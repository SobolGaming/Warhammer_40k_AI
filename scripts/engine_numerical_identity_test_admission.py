"""Finite numerical-identity source admission over the retained speedup transition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.behavioral_selection_members import (
    _selection_members,
    _selection_no_links,
    _selection_object,
)
from scripts.canonical_circle_test_admission import ADDITION as CIRCLE_ADDITION
from scripts.canonical_circle_test_admission import ADDITION_SHA256 as CIRCLE_SHA256
from scripts.canonical_polygon_pairs_test_admission import ADDITION as PAIRS_ADDITION
from scripts.canonical_polygon_pairs_test_admission import ADDITION_SHA256 as PAIRS_ADDITION_SHA256
from scripts.canonical_polygon_queries_test_admission import ADDITION as QUERIES_ADDITION
from scripts.canonical_polygon_queries_test_admission import (
    ADDITION_SHA256 as QUERIES_ADDITION_SHA256,
)
from scripts.canonical_polygon_test_admission import ADDITION as POLYGON_ADDITION
from scripts.canonical_polygon_test_admission import ADDITION_SHA256 as POLYGON_SHA256
from scripts.exact_contact_test_admission import ADDITION as CONTACT_ADDITION
from scripts.exact_contact_test_admission import ADDITION_SHA256 as CONTACT_ADDITION_SHA256
from scripts.milli_inch_test_admission import (
    ADDITION as FOUNDATION_ADDITION,
)
from scripts.milli_inch_test_admission import (
    ADDITION_SHA256 as FOUNDATION_SHA256,
)
from scripts.milli_inch_test_admission import (
    MANIFEST,
    RETAINED_CUTOVER_SHA256,
)
from scripts.milli_inch_test_admission import (
    SOURCE as FOUNDATION_SOURCE,
)
from scripts.milli_inch_test_admission import (
    SOURCE_SHA256 as FOUNDATION_SOURCE_SHA256,
)
from scripts.precision_profile_test_admission import ADDITION as PROFILE_ADDITION
from scripts.precision_profile_test_admission import ADDITION_SHA256 as PROFILE_SHA256
from scripts.symbolic_milli_inch_test_admission import ADDITION as SYMBOLIC_ADDITION
from scripts.symbolic_milli_inch_test_admission import ADDITION_SHA256 as SYMBOLIC_SHA256

ADDITION = "data/source_audits/ci64_provenance_v1/engine-numerical-identity-test-transition-v1.json"
ADDITION_SHA256 = "4ab08b326285715c00a3bd10aabca1f6572da4fdfa55958309a2e2a215668bb8"
RUNTIME = "d60a6871e475632bdf930a80251f39e7bae5b5f40c35960b6ed1790750f62fa0"
COORDINATES = "src/warhammer40k_core/geometry/numerical_identity.py"
QUERIES = "src/warhammer40k_core/geometry/milli_inch_polygon_queries.py"
QUERIES_SHA256 = "e46fe8e9738786931c565c5ea5a2dc2921132e3690b420632bfcb8a00c362cc5"
SOURCE = "src/warhammer40k_core/engine/numerical_identity.py"
OWNER = "tests/rules/section01/test_engine_numerical_identity.py"
EXACT_MOVEMENT_ADDITION = (
    "data/source_audits/ci64_provenance_v1/exact-movement-test-transition-v1.json"
)
EXACT_MOVEMENT_SHA256 = "ada2ae25f047f949b9faf3b2c33d7cc590b4c6bc9f22911dc8acb8b5ec5e4b2b"
EXACT_MOVEMENT_OWNER = "tests/rules/section01/test_exact_movement.py"
_EXACT_MOVEMENT_SOURCES = (
    "src/warhammer40k_core/engine/exact_movement.py",
    "src/warhammer40k_core/geometry/exact_path.py",
    "src/warhammer40k_core/geometry/exact_pose.py",
)
CIRCLE_POLYGON_ADDITION = (
    "data/source_audits/ci64_provenance_v1/circle-polygon-test-addition-v1.json"
)
CIRCLE_POLYGON_SHA256 = "617f67340b0d7e5cd8f1d2786faa193a96bbc7f2fa18f3b8b7988bc263458a91"
CIRCLE_POLYGON_OWNER = "tests/rules/section01/test_milli_inch_circle_polygon.py"
_CIRCLE_POLYGON_SOURCE = "src/warhammer40k_core/geometry/milli_inch_circle_polygon.py"

OVAL_POINT_ADDITION = "data/source_audits/ci64_provenance_v1/oval-point-test-addition-v1.json"
OVAL_POINT_SHA256 = "c90a008c3d213364cfa9085b27d864b301543b7a35dabb94175870cb1c42cbd9"
OVAL_POINT_OWNER = "tests/rules/section01/test_milli_inch_oval.py"
_OVAL_POINT_SOURCE = "src/warhammer40k_core/geometry/milli_inch_oval.py"

OVAL_POLYGON_ADDITION = "data/source_audits/ci64_provenance_v1/oval-polygon-test-addition-v1.json"
OVAL_POLYGON_SHA256 = "bada04a93ba349277cb172ca65d1caec1ccf59f7ea943b3eb08b6efb8e3f9b87"
OVAL_POLYGON_OWNER = "tests/rules/section01/test_milli_inch_oval_polygon.py"
_OVAL_POLYGON_SOURCE = "src/warhammer40k_core/geometry/milli_inch_oval_polygon.py"

OVAL_POLYGON_GAP_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/oval-polygon-gap-test-transition-v1.json"
)
OVAL_POLYGON_GAP_SHA256 = "aa14d37c70228c1369c6a534b0ba1e982513dc3bd0fff6bf2a6edcddef403ad5"
OVAL_POLYGON_GAP_OWNER = "tests/rules/section01/test_milli_inch_oval_polygon_distance.py"

CIRCLE_OVAL_TRANSITION = "data/source_audits/ci64_provenance_v1/circle-oval-test-transition-v1.json"
CIRCLE_OVAL_SHA256 = "8145f8eae6477e8e702b7804d770974f6337e6855940d7468eba3c1ec0e0d6b5"
CIRCLE_OVAL_OWNER = "tests/rules/section01/test_milli_inch_circle_oval.py"
_CIRCLE_OVAL_SOURCE = "src/warhammer40k_core/geometry/milli_inch_circle_oval.py"


OVAL_OVAL_TOPOLOGY_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/oval-oval-topology-test-transition-v1.json"
)
OVAL_OVAL_TOPOLOGY_SHA256 = "82797a1bb5efb5b3928a51d7f09fb631bba56267f32b26cd3c1685dd0ac5fbb7"
OVAL_OVAL_TOPOLOGY_OWNER = "tests/rules/section01/test_milli_inch_oval_oval.py"
_OVAL_OVAL_TOPOLOGY_SOURCE = "src/warhammer40k_core/geometry/milli_inch_oval_oval.py"


OVAL_OVAL_GAP_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/oval-oval-gap-test-transition-v1.json"
)
OVAL_OVAL_GAP_SHA256 = "1a454ad230db5f586d952b1b362038a6ef36ced48e13434e9871ee97c75eed10"
OVAL_OVAL_GAP_OWNER = "tests/rules/section01/test_milli_inch_oval_oval_distance.py"
_OVAL_OVAL_GAP_SOURCE = "src/warhammer40k_core/geometry/milli_inch_oval_oval_distance.py"


OVAL_OVAL_WITNESS_ADDITION = (
    "data/source_audits/ci64_provenance_v1/oval-oval-witness-test-addition-v1.json"
)
OVAL_OVAL_WITNESS_SHA256 = "b55763903095916ca0082e36ce7a24ac2515a4a0e53516dbd86028af5687aa0d"
OVAL_OVAL_WITNESS_OWNER = "tests/rules/section01/test_milli_inch_oval_oval_witnesses.py"

OVAL_CODEC_TRANSITION = "data/source_audits/ci64_provenance_v1/oval-codec-test-transition-v1.json"
OVAL_CODEC_SHA256 = "b7bdb26dd433d2b87d0f488ffd054f6bb41592f6ac23865c66c5ccd0ec273057"
OVAL_CODEC_OWNER = "tests/rules/section01/test_milli_inch_oval_payload.py"


GAMEPLAY_BUDGET_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/gameplay-movement-budget-test-transition-v1.json"
)
GAMEPLAY_BUDGET_SHA256 = "16fea4c0dd316cc1a1499e31ae211d7f172696bc8e74deee857f27ed388ea962"
GAMEPLAY_BUDGET_OWNER = "tests/rules/section03/test_facade.py"
GAMEPLAY_CHARGE_OWNER = "tests/rules/section11/test_moves.py"
GAMEPLAY_ESCAPE_OWNER = "tests/rules/section09/test_fall_back.py"
GAMEPLAY_SORCERER_OWNER = "tests/factions/emperors_children/test_selected_consumers.py"

STAGE2_FIGHT_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-fight-cover-test-transition-v1.json"
)
STAGE2_FIGHT_SHA256 = "0a5a29ce7741dc63e2c70633fbc672c34d95e6668f6ec81cf6a0b65238619b79"
STAGE2_FIGHT_BASE = "292bf8a55e184392f7d62d245707c8c1b7c0f9db"
STAGE2_FIGHT_SOURCE = "src/warhammer40k_core/engine/attack_sequence_damage_resolution.py"
STAGE2_FIGHT_OWNER = "tests/rules/section05/test_allocation_choices.py"
COUNTEROFFENSIVE_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-counteroffensive-test-transition-v1.json"
)
COUNTEROFFENSIVE_SHA256 = "cf6787bd0b721d025478c6126e3dccbc9d5b3bb8822fce331313d9ce5dd62ad3"
COUNTEROFFENSIVE_BASE = "d190560f0291479429ae92c222109259a43533df"
COUNTEROFFENSIVE_OWNER = "tests/rules/section15/test_reactions.py"
STAGE2_MELEE_RESTORE_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-melee-restore-test-transition-v1.json"
)
STAGE2_MELEE_RESTORE_SHA256 = "51e236eb87282d6c27ac2c59fb33f4cece708babac87ab4f1a181ee9b16a8b31"
STAGE2_MELEE_RESTORE_BASE = "7dd6fc770ce122a1a42b601eabeaf44e14bc8c82"
STAGE2_MELEE_RESTORE_SOURCE = "src/warhammer40k_core/engine/lifecycle_reaction_queue.py"
STAGE2_MELEE_HISTORY_SOURCE = "src/warhammer40k_core/engine/melee_commitment_history.py"
STAGE2_MELEE_FRAME_SOURCE = "src/warhammer40k_core/engine/reaction_queue.py"

STAGE2_FIGHT_REROLL_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-fight-reroll-test-transition-v1.json"
)
STAGE2_FIGHT_REROLL_SHA256 = "9b48614e7f5b8831a1e1b5ba21d1791b9cbc0ddc5055d9de3a14bf6d053c5ab6"
STAGE2_FIGHT_REROLL_BASE = "ca0da3d36731986ed55b623d9f82c05e6eda5560"
STAGE2_FIGHT_REROLL_SOURCE = "src/warhammer40k_core/engine/lifecycle.py"
STAGE2_FIGHT_REROLL_FIXTURE = "tests/order135_counteroffensive_helpers.py"


TERMINAL_RESTORE_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/terminal-restore-test-transition-v1.json"
)
TERMINAL_RESTORE_SHA256 = "58f3ce92764f2dce0a62d5a00b0cb6bf820aebddd690e817bdcc8641707f27ce"
TERMINAL_RESTORE_BASE = "545d5556c279f88ffaaa897941245ca093e8e9f6"
TERMINAL_RESTORE_SOURCES = (
    "src/warhammer40k_core/engine/normal_move_history.py",
    "src/warhammer40k_core/engine/enhancement_effects.py",
)
TERMINAL_RESTORE_OWNERS = (
    "tests/rules/section09/test_restrictions.py",
    "tests/rules/rules01/unit/test_unit_splitting.py",
)


CAVALCADE_AUTHORITY_RUNTIME = "4a144491e2ca85593c31db4a5a6318ccb32b4247c5d873b8d21471e0c019d64f"
CAVALCADE_AUTHORITY_SOURCES = {
    "src/warhammer40k_core/engine/battle_shock_hooks.py": (
        "4f149f2664ac363aa9034c3924c43c7f1356c82dc27cdd2c32467b163ec4f99b"
    ),
    (
        "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
        "chaos_daemons/battle_shock_outcome_authority.py"
    ): "15e25a9bc3587826c6a4be6928cb33ddcfa4a32460273aa7a7ae8ce9cccd76ba",
    "src/warhammer40k_core/engine/mutation_decision_authority.py": (
        "571fc86485651347b5ef326e8682c9d614db8a2b203a9cd61ec2f827da669ce7"
    ),
    "src/warhammer40k_core/engine/runtime_read_only.py": (
        "9e10d35c6941da7e3bcdea3ec2efb4239a0a403763776c9dbddc5e6051984630"
    ),
    "src/warhammer40k_core/engine/turn_end_hooks.py": (
        "83b66ad158b37385914be58f5a0c20365e0a1a852aab60fcec6f62ab05aa4bbc"
    ),
}


ROUND_FIVE_SHADOW_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/round-five-shadow-test-transition-v1.json"
)
ROUND_FIVE_SHADOW_SHA256 = "b98c215658e87a400c6440d58ce5da0ec08f23d13ebc1c9345716f006b57d2ea"
ROUND_FIVE_SHADOW_BASE = "7d8c559b9901c9ad2233b87cf3bf151cb4c35476"
ROUND_FIVE_SHADOW_OWNER = "tests/factions/chaos_daemons/unit/test_bloodcrushers_abilities.py"
ROUND_FIVE_SHADOW_SOURCES = (
    "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/chaos_daemons/army_rule.py",
    "src/warhammer40k_core/engine/rule_aura_resolution.py",
)


CLOSE_QUARTERS_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/round-five-close-quarters-test-transition-v1.json"
)
CLOSE_QUARTERS_SHA256 = "12198bd19d8c8fc191525cee5499a579a1018a599590a31897551e8679527b91"
CLOSE_QUARTERS_BASE = "466071748906e366c2a4aac73231728ea4123c20"
CLOSE_QUARTERS_OWNER = "tests/rules/section06/test_visibility.py"
CLOSE_QUARTERS_SOURCES = (
    "src/warhammer40k_core/geometry/continuous_visibility.py",
    "src/warhammer40k_core/geometry/visibility_witnesses.py",
)


STRICT_REPLAY_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-strict-replay-test-transition-v1.json"
)
STRICT_REPLAY_SHA256 = "c052fbc19a1647aa855cc26b0bfb909230ca485c63fb47c6425caf0ee46c4f89"
STRICT_REPLAY_BASE = "a61e1b27ce13f87ebe4e2f1ae23eb6701c38ccf7"
STRICT_REPLAY_OWNER = "tests/rules/section21/test_persistence.py"
STRICT_REPLAY_SOURCES = ("src/warhammer40k_core/adapters/local_session.py",)


ALLOCATION_COHERENCY_ADDITION = (
    "data/source_audits/ci64_provenance_v1/stage2-allocation-coherency-test-addition-v1.json"
)
ALLOCATION_COHERENCY_SHA256 = "4dee9b64424aedb21324016b9f1e430847fdda5e2a409229b50e8a23f0fb8981"
ALLOCATION_COHERENCY_OWNER = "tests/infrastructure/adapters/test_allocation_coherency.py"
ALLOCATION_COHERENCY_POLICY = "src/warhammer40k_core/ai/allocation_coherency.py"


COVER_EVENT_IDENTITY_ADDITION = (
    "data/source_audits/ci64_provenance_v1/stage2-cover-event-identity-test-addition-v1.json"
)
COVER_EVENT_IDENTITY_SHA256 = "cb6b967544fb2b54878b8021dbcb26d47a7625c12158f77aabb16a1bdd31801f"
COVER_EVENT_IDENTITY_BASE = "7d0d2e320ff7b564b87aafbca368bbab00c325b6"
COVER_EVENT_IDENTITY_SOURCE = "src/warhammer40k_core/adapters/viewer_identity.py"
COVER_EVENT_IDENTITY_OWNER = "tests/infrastructure/adapters/test_cover_event_identity.py"


type SourceSuccessors = dict[str, dict[str, str]]
type TestSuccessors = dict[str, dict[str, object]]


type TestTransition = tuple[dict[str, dict[str, object]], dict[str, dict[str, object]], bytes]


def _checked_bytes(root: Path, name: str, digest: str) -> bytes:
    _selection_no_links(root, root / name)
    if not (root / name).is_file():
        raise SystemExit("Missing numerical identity test transition source: " + name)
    raw = (root / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise SystemExit("Numerical identity test transition source bytes differ: " + name)
    return raw


def _gameplay_budget_successor(
    root: Path,
    *,
    current_tests: TestSuccessors,
    current_sources: SourceSuccessors,
) -> tuple[str, SourceSuccessors, TestSuccessors, bytes]:
    raw = _checked_bytes(root, GAMEPLAY_BUDGET_TRANSITION, GAMEPLAY_BUDGET_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {"schema", "retained_oval_codec_sha256", "runtime_fingerprint", "sources", "tests"}
        or record["schema"] != "finite-gameplay-movement-budget-test-transition-v1"
        or record["retained_oval_codec_sha256"] != OVAL_CODEC_SHA256
        or set(record["tests"])
        != {
            GAMEPLAY_BUDGET_OWNER,
            GAMEPLAY_CHARGE_OWNER,
            GAMEPLAY_ESCAPE_OWNER,
            GAMEPLAY_SORCERER_OWNER,
            "tests/infrastructure/adapters/test_canonical_deployment_coverage.py",
            OWNER,
            "tests/infrastructure/adapters/unit/test_linux_authority.py",
            "tests/infrastructure/adapters/unit/test_numerical_policy.py",
            "tests/rules/section18/test_facade.py",
        }
    ):
        raise SystemExit("Gameplay movement budget test transition membership differs.")
    for name, change in record["sources"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit("Gameplay budget transition requires exact before and after digests.")
        _retained_source(root, name, change["after"], current_sources)
    successors = _selection_members(record["tests"], root, current=current_tests)
    return record["runtime_fingerprint"], record["sources"], successors, raw


def _stage2_fight_successor(root: Path) -> tuple[str, TestSuccessors, bytes]:
    raw = _checked_bytes(root, STAGE2_FIGHT_TRANSITION, STAGE2_FIGHT_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_gameplay_budget_sha256",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-stage2-fight-cover-test-transition-v1"
        or record["base"] != STAGE2_FIGHT_BASE
        or record["retained_gameplay_budget_sha256"] != GAMEPLAY_BUDGET_SHA256
        or set(record["source"]) != {STAGE2_FIGHT_SOURCE}
        or set(record["test"]) != {STAGE2_FIGHT_OWNER, GAMEPLAY_SORCERER_OWNER}
    ):
        raise SystemExit("Stage 2 Fight Cover test transition membership differs.")
    _checked_bytes(root, STAGE2_FIGHT_SOURCE, record["source"][STAGE2_FIGHT_SOURCE]["after"])
    tests = _selection_members({name: row["after"] for name, row in record["test"].items()}, root)
    return record["runtime_fingerprint"], tests, raw


def _counteroffensive_test_successor(
    root: Path, runtime: str, *, current_tests: TestSuccessors | None
) -> tuple[TestSuccessors, bytes]:
    raw = _checked_bytes(root, COUNTEROFFENSIVE_TRANSITION, COUNTEROFFENSIVE_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {"schema", "base", "retained_stage2_fight_cover_sha256", "runtime_fingerprint", "test"}
        or record["schema"] != "finite-stage2-counteroffensive-test-transition-v1"
        or record["base"] != COUNTEROFFENSIVE_BASE
        or record["retained_stage2_fight_cover_sha256"] != STAGE2_FIGHT_SHA256
        or record["runtime_fingerprint"] != runtime
        or set(record["test"]) != {COUNTEROFFENSIVE_OWNER}
    ):
        raise SystemExit("Stage 2 Counteroffensive test transition membership differs.")
    tests = _selection_members(
        {name: row["after"] for name, row in record["test"].items()},
        root,
        current=current_tests,
    )
    return tests, raw


def _stage2_melee_restore_successor(
    root: Path, *, current_tests: TestSuccessors | None
) -> tuple[str, TestSuccessors, bytes]:
    raw = _checked_bytes(root, STAGE2_MELEE_RESTORE_TRANSITION, STAGE2_MELEE_RESTORE_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_counteroffensive_sha256",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-stage2-melee-restore-test-transition-v1"
        or record["base"] != STAGE2_MELEE_RESTORE_BASE
        or record["retained_counteroffensive_sha256"] != COUNTEROFFENSIVE_SHA256
        or set(record["source"])
        != {STAGE2_MELEE_RESTORE_SOURCE, STAGE2_MELEE_HISTORY_SOURCE, STAGE2_MELEE_FRAME_SOURCE}
        or set(record["test"]) != {COUNTEROFFENSIVE_OWNER}
    ):
        raise SystemExit("Stage 2 melee restore test transition membership differs.")
    for name, change in record["source"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit(
                "Stage 2 melee restore requires exact before and after source digests."
            )
        _checked_bytes(root, name, change["after"])
    tests = _selection_members(
        {name: row["after"] for name, row in record["test"].items()},
        root,
        current=current_tests,
    )
    return record["runtime_fingerprint"], tests, raw


def _stage2_fight_reroll_successor(
    root: Path,
) -> tuple[str, TestSuccessors, bytes, SourceSuccessors]:
    raw = _checked_bytes(root, STAGE2_FIGHT_REROLL_TRANSITION, STAGE2_FIGHT_REROLL_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_melee_restore_sha256",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-stage2-fight-reroll-test-transition-v1"
        or record["base"] != STAGE2_FIGHT_REROLL_BASE
        or record["retained_melee_restore_sha256"] != STAGE2_MELEE_RESTORE_SHA256
        or set(record["source"]) != {STAGE2_FIGHT_REROLL_SOURCE, STAGE2_FIGHT_REROLL_FIXTURE}
        or set(record["test"]) != {COUNTEROFFENSIVE_OWNER}
    ):
        raise SystemExit("Stage 2 Fight reroll test transition membership differs.")
    for name, change in record["source"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit("Stage 2 Fight reroll requires exact before and after source digests.")
        _checked_bytes(root, name, change["after"])
    melee_restore = json.loads(
        _checked_bytes(root, STAGE2_MELEE_RESTORE_TRANSITION, STAGE2_MELEE_RESTORE_SHA256),
        object_pairs_hook=_selection_object,
    )
    test = record["test"][COUNTEROFFENSIVE_OWNER]
    if (
        set(test) != {"before", "after"}
        or test["before"] != (melee_restore["test"][COUNTEROFFENSIVE_OWNER]["after"])
    ):
        raise SystemExit("Stage 2 Fight reroll test predecessor differs.")
    tests = _selection_members({COUNTEROFFENSIVE_OWNER: test["after"]}, root)
    return (
        record["runtime_fingerprint"],
        tests,
        raw,
        {STAGE2_FIGHT_REROLL_SOURCE: record["source"][STAGE2_FIGHT_REROLL_SOURCE]},
    )


def _terminal_restore_successor(root: Path) -> tuple[str, TestSuccessors, bytes]:
    raw = _checked_bytes(root, TERMINAL_RESTORE_TRANSITION, TERMINAL_RESTORE_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_fight_reroll_sha256",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-terminal-restore-test-transition-v1"
        or record["base"] != TERMINAL_RESTORE_BASE
        or record["retained_fight_reroll_sha256"] != STAGE2_FIGHT_REROLL_SHA256
        or set(record["source"]) != set(TERMINAL_RESTORE_SOURCES)
        or set(record["test"]) != set(TERMINAL_RESTORE_OWNERS)
    ):
        raise SystemExit("Terminal restore test transition membership differs.")
    for name, source in record["source"].items():
        if set(source) != {"before", "after"}:
            raise SystemExit("Terminal restore requires exact before and after source digests.")
        _checked_bytes(root, name, source["after"])
    if any(set(test) != {"before", "after"} for test in record["test"].values()):
        raise SystemExit("Terminal restore requires exact before and after test digests.")
    tests = _selection_members({name: test["after"] for name, test in record["test"].items()}, root)
    return record["runtime_fingerprint"], tests, raw


def _retained_source(root: Path, name: str, digest: str, successors: SourceSuccessors) -> None:
    if name in successors:
        if successors[name]["before"] != digest:
            raise SystemExit("Gameplay movement budget source preimage differs: " + name)
        return
    _checked_bytes(root, name, digest)


def engine_numerical_identity_test_transition(
    root: Path, retained_cutover_sha256: str
) -> TestTransition | None:
    """Admit one exact owner while retaining every predecessor source inventory."""
    return _identity_test_transition(root, retained_cutover_sha256, runtime=RUNTIME)


def exact_movement_test_transition(
    root: Path, retained_cutover_sha256: str
) -> TestTransition | None:
    """Admit the flat-disk movement cases without modifying predecessor evidence."""
    paths = (EXACT_MOVEMENT_ADDITION, EXACT_MOVEMENT_OWNER, *_EXACT_MOVEMENT_SOURCES)
    for path in paths:
        _selection_no_links(root, root / path)
    successor_paths = (CIRCLE_POLYGON_ADDITION, CIRCLE_POLYGON_OWNER, _CIRCLE_POLYGON_SOURCE)
    for path in successor_paths:
        _selection_no_links(root, root / path)
    has_circle_polygon = any((root / path).exists() for path in successor_paths)
    oval_paths = (OVAL_POINT_ADDITION, OVAL_POINT_OWNER, _OVAL_POINT_SOURCE)
    for path in oval_paths:
        _selection_no_links(root, root / path)
    has_oval_point = any((root / path).exists() for path in oval_paths)
    oval_polygon_paths = (OVAL_POLYGON_ADDITION, OVAL_POLYGON_OWNER, _OVAL_POLYGON_SOURCE)
    for path in oval_polygon_paths:
        _selection_no_links(root, root / path)
    has_oval_polygon = any((root / path).exists() for path in oval_polygon_paths)
    gap_paths = (OVAL_POLYGON_GAP_TRANSITION, OVAL_POLYGON_GAP_OWNER)
    for path in gap_paths:
        _selection_no_links(root, root / path)
    has_gap = any((root / path).exists() for path in gap_paths)
    circle_oval_paths = (CIRCLE_OVAL_TRANSITION, CIRCLE_OVAL_OWNER, _CIRCLE_OVAL_SOURCE)
    for path in circle_oval_paths:
        _selection_no_links(root, root / path)
    has_circle_oval = any((root / path).exists() for path in circle_oval_paths)
    oval_oval_paths = (
        OVAL_OVAL_TOPOLOGY_TRANSITION,
        OVAL_OVAL_TOPOLOGY_OWNER,
        _OVAL_OVAL_TOPOLOGY_SOURCE,
    )
    for path in oval_oval_paths:
        _selection_no_links(root, root / path)
    has_oval_oval = any((root / path).exists() for path in oval_oval_paths)
    oval_gap_paths = (OVAL_OVAL_GAP_TRANSITION, OVAL_OVAL_GAP_OWNER, _OVAL_OVAL_GAP_SOURCE)
    for path in oval_gap_paths:
        _selection_no_links(root, root / path)
    has_oval_gap = any((root / path).exists() for path in oval_gap_paths)
    witness_paths = (OVAL_OVAL_WITNESS_ADDITION, OVAL_OVAL_WITNESS_OWNER)
    for path in witness_paths:
        _selection_no_links(root, root / path)
    has_witnesses = any((root / path).exists() for path in witness_paths)
    codec_paths = (OVAL_CODEC_TRANSITION, OVAL_CODEC_OWNER)
    for path in codec_paths:
        _selection_no_links(root, root / path)
    has_codec = any((root / path).exists() for path in codec_paths)
    budget_path = root / GAMEPLAY_BUDGET_TRANSITION
    fight_path = root / STAGE2_FIGHT_TRANSITION
    counteroffensive_path = root / COUNTEROFFENSIVE_TRANSITION
    melee_restore_path = root / STAGE2_MELEE_RESTORE_TRANSITION
    fight_reroll_path = root / STAGE2_FIGHT_REROLL_TRANSITION
    _selection_no_links(root, budget_path)
    _selection_no_links(root, fight_path)
    _selection_no_links(root, counteroffensive_path)
    _selection_no_links(root, melee_restore_path)
    _selection_no_links(root, fight_reroll_path)
    has_gameplay_budget = budget_path.exists()
    has_stage2_fight = fight_path.exists()
    has_counteroffensive = counteroffensive_path.exists()
    has_melee_restore = melee_restore_path.exists()
    has_fight_reroll = fight_reroll_path.exists()
    terminal_restore_path = root / TERMINAL_RESTORE_TRANSITION
    _selection_no_links(root, terminal_restore_path)
    has_terminal_restore = terminal_restore_path.exists()
    if has_terminal_restore and not has_fight_reroll:
        raise SystemExit("Terminal restore tests require the Fight reroll predecessor.")
    if has_fight_reroll and not has_melee_restore:
        raise SystemExit("Stage 2 Fight reroll tests require the melee restore predecessor.")
    if has_melee_restore and not has_counteroffensive:
        raise SystemExit("Stage 2 melee restore tests require the Counteroffensive predecessor.")
    if has_counteroffensive and not has_stage2_fight:
        raise SystemExit("Stage 2 Counteroffensive tests require the Fight Cover predecessor.")
    if has_stage2_fight and not (has_gameplay_budget and has_codec):
        raise SystemExit(
            "Stage 2 Fight Cover tests require the gameplay movement budget predecessor."
        )
    if has_codec and not has_witnesses:
        raise SystemExit("Oval codec tests require the oval-oval witness predecessor.")
    if has_witnesses and not has_oval_gap:
        raise SystemExit("Oval-oval witness tests require their oval-oval gap predecessor.")
    if has_oval_gap and not has_oval_oval:
        raise SystemExit("Oval-oval gap tests require their oval-oval topology predecessor.")
    if has_oval_oval and not has_circle_oval:
        raise SystemExit("Oval-oval topology tests require their circle-oval predecessor.")
    if has_circle_oval and not has_gap:
        raise SystemExit("Circle-oval tests require their oval-polygon gap predecessor.")
    if has_gap and not has_oval_polygon:
        raise SystemExit("Oval-polygon gap tests require their topology predecessor.")
    if has_oval_polygon and not has_oval_point:
        raise SystemExit("Oval-polygon test addition requires its oval point predecessor.")
    if has_oval_point and not has_circle_polygon:
        raise SystemExit("Oval point test addition requires its circle-polygon predecessor.")
    if not has_circle_polygon and not any((root / path).exists() for path in paths):
        return None
    raw = _checked_bytes(root, EXACT_MOVEMENT_ADDITION, EXACT_MOVEMENT_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {"schema", "retained_identity_sha256", "runtime_fingerprint", "sources", "added_files"}
        or record["schema"] != "finite-exact-movement-test-transition-v1"
        or record["retained_identity_sha256"] != ADDITION_SHA256
        or set(record["sources"]) != set(_EXACT_MOVEMENT_SOURCES)
        or set(record["added_files"]) != {EXACT_MOVEMENT_OWNER}
    ):
        raise SystemExit("Exact movement test transition membership differs.")
    for name, digest in record["sources"].items():
        _checked_bytes(root, name, digest)
    runtime = record["runtime_fingerprint"]
    additions = _selection_members(record["added_files"], root)
    if has_circle_polygon:
        next_raw = _checked_bytes(root, CIRCLE_POLYGON_ADDITION, CIRCLE_POLYGON_SHA256)
        successor = json.loads(next_raw, object_pairs_hook=_selection_object)
        if (
            successor.keys() != {"schema", "runtime_fingerprint", "source_sha256", "added_files"}
            or successor["schema"] != "finite-circle-polygon-test-addition-v1"
            or set(successor["added_files"]) != {CIRCLE_POLYGON_OWNER}
        ):
            raise SystemExit("Circle-polygon test addition membership differs.")
        _checked_bytes(root, _CIRCLE_POLYGON_SOURCE, successor["source_sha256"])
        additions.update(_selection_members(successor["added_files"], root))
        runtime = successor["runtime_fingerprint"]
        raw += b"\0" + next_raw
    if has_oval_point:
        oval_raw = _checked_bytes(root, OVAL_POINT_ADDITION, OVAL_POINT_SHA256)
        oval = json.loads(oval_raw, object_pairs_hook=_selection_object)
        if (
            oval.keys() != {"schema", "runtime_fingerprint", "source_sha256", "added_files"}
            or oval["schema"] != "finite-oval-point-test-addition-v1"
            or set(oval["added_files"]) != {OVAL_POINT_OWNER}
        ):
            raise SystemExit("Oval point test addition membership differs.")
        if not has_gap:
            _checked_bytes(root, _OVAL_POINT_SOURCE, oval["source_sha256"])
        additions.update(_selection_members(oval["added_files"], root))
        runtime = oval["runtime_fingerprint"]
        raw += b"\0" + oval_raw
    if has_oval_polygon:
        polygon_raw = _checked_bytes(root, OVAL_POLYGON_ADDITION, OVAL_POLYGON_SHA256)
        polygon = json.loads(polygon_raw, object_pairs_hook=_selection_object)
        if (
            polygon.keys() != {"schema", "runtime_fingerprint", "source_sha256", "added_files"}
            or polygon["schema"] != "finite-oval-polygon-test-addition-v1"
            or set(polygon["added_files"]) != {OVAL_POLYGON_OWNER}
        ):
            raise SystemExit("Oval-polygon test addition membership differs.")
        if not has_gap:
            _checked_bytes(root, _OVAL_POLYGON_SOURCE, polygon["source_sha256"])
        additions.update(_selection_members(polygon["added_files"], root))
        runtime = polygon["runtime_fingerprint"]
        raw += b"\0" + polygon_raw
    if has_gap:
        gap_raw = _checked_bytes(root, OVAL_POLYGON_GAP_TRANSITION, OVAL_POLYGON_GAP_SHA256)
        gap = json.loads(gap_raw, object_pairs_hook=_selection_object)
        if (
            gap.keys()
            != {
                "schema",
                "runtime_fingerprint",
                "retained_oval_polygon_sha256",
                "sources",
                "added_files",
            }
            or gap["schema"] != "finite-oval-polygon-gap-test-transition-v1"
            or gap["retained_oval_polygon_sha256"] != OVAL_POLYGON_SHA256
            or set(gap["sources"]) != {_OVAL_POINT_SOURCE, _OVAL_POLYGON_SOURCE}
            or set(gap["added_files"]) != {OVAL_POLYGON_GAP_OWNER}
        ):
            raise SystemExit("Oval-polygon gap test transition membership differs.")
        for name, digest in gap["sources"].items():
            if name != _OVAL_POINT_SOURCE or not has_circle_oval:
                _checked_bytes(root, name, digest)
        additions.update(_selection_members(gap["added_files"], root))
        runtime = gap["runtime_fingerprint"]
        raw += b"\0" + gap_raw
    if has_circle_oval:
        circle_oval_raw = _checked_bytes(root, CIRCLE_OVAL_TRANSITION, CIRCLE_OVAL_SHA256)
        circle_oval = json.loads(circle_oval_raw, object_pairs_hook=_selection_object)
        if (
            circle_oval.keys()
            != {
                "schema",
                "runtime_fingerprint",
                "retained_oval_polygon_gap_sha256",
                "sources",
                "added_files",
            }
            or circle_oval["schema"] != "finite-circle-oval-test-transition-v1"
            or circle_oval["retained_oval_polygon_gap_sha256"] != OVAL_POLYGON_GAP_SHA256
            or set(circle_oval["sources"]) != {_OVAL_POINT_SOURCE, _CIRCLE_OVAL_SOURCE}
            or set(circle_oval["added_files"]) != {CIRCLE_OVAL_OWNER}
        ):
            raise SystemExit("Circle-oval test transition membership differs.")
        for name, digest in circle_oval["sources"].items():
            if name != _OVAL_POINT_SOURCE or not has_codec:
                _checked_bytes(root, name, digest)
        additions.update(_selection_members(circle_oval["added_files"], root))
        runtime = circle_oval["runtime_fingerprint"]
        raw += b"\0" + circle_oval_raw
    if has_oval_oval:
        oval_oval_raw = _checked_bytes(
            root, OVAL_OVAL_TOPOLOGY_TRANSITION, OVAL_OVAL_TOPOLOGY_SHA256
        )
        oval_oval = json.loads(oval_oval_raw, object_pairs_hook=_selection_object)
        if (
            oval_oval.keys()
            != {
                "schema",
                "runtime_fingerprint",
                "retained_circle_oval_sha256",
                "sources",
                "added_files",
            }
            or oval_oval["schema"] != "finite-oval-oval-topology-test-transition-v1"
            or oval_oval["retained_circle_oval_sha256"] != CIRCLE_OVAL_SHA256
            or set(oval_oval["sources"]) != {_OVAL_OVAL_TOPOLOGY_SOURCE}
            or set(oval_oval["added_files"]) != {OVAL_OVAL_TOPOLOGY_OWNER}
        ):
            raise SystemExit("Oval-oval topology test transition membership differs.")
        _checked_bytes(
            root, _OVAL_OVAL_TOPOLOGY_SOURCE, oval_oval["sources"][_OVAL_OVAL_TOPOLOGY_SOURCE]
        )
        additions.update(_selection_members(oval_oval["added_files"], root))
        runtime = oval_oval["runtime_fingerprint"]
        raw += b"\0" + oval_oval_raw
    if has_oval_gap:
        oval_gap_raw = _checked_bytes(root, OVAL_OVAL_GAP_TRANSITION, OVAL_OVAL_GAP_SHA256)
        oval_gap = json.loads(oval_gap_raw, object_pairs_hook=_selection_object)
        if (
            oval_gap.keys()
            != {
                "schema",
                "runtime_fingerprint",
                "retained_oval_oval_topology_sha256",
                "sources",
                "added_files",
            }
            or oval_gap["schema"] != "finite-oval-oval-gap-test-transition-v1"
            or oval_gap["retained_oval_oval_topology_sha256"] != OVAL_OVAL_TOPOLOGY_SHA256
            or set(oval_gap["sources"]) != {_OVAL_OVAL_GAP_SOURCE}
            or set(oval_gap["added_files"]) != {OVAL_OVAL_GAP_OWNER}
        ):
            raise SystemExit("Oval-oval gap test transition membership differs.")
        _checked_bytes(root, _OVAL_OVAL_GAP_SOURCE, oval_gap["sources"][_OVAL_OVAL_GAP_SOURCE])
        additions.update(_selection_members(oval_gap["added_files"], root))
        runtime = oval_gap["runtime_fingerprint"]
        raw += b"\0" + oval_gap_raw
    if has_witnesses:
        witness_raw = _checked_bytes(root, OVAL_OVAL_WITNESS_ADDITION, OVAL_OVAL_WITNESS_SHA256)
        witness = json.loads(witness_raw, object_pairs_hook=_selection_object)
        if (
            witness.keys()
            != {"schema", "runtime_fingerprint", "retained_oval_oval_gap_sha256", "added_files"}
            or witness["schema"] != "finite-oval-oval-witness-test-addition-v1"
            or witness["retained_oval_oval_gap_sha256"] != OVAL_OVAL_GAP_SHA256
            or witness["runtime_fingerprint"] != runtime
            or set(witness["added_files"]) != {OVAL_OVAL_WITNESS_OWNER}
        ):
            raise SystemExit("Oval-oval witness test addition membership differs.")
        additions.update(_selection_members(witness["added_files"], root))
        raw += b"\0" + witness_raw
    if has_codec:
        codec_raw = _checked_bytes(root, OVAL_CODEC_TRANSITION, OVAL_CODEC_SHA256)
        codec = json.loads(codec_raw, object_pairs_hook=_selection_object)
        if (
            codec.keys()
            != {
                "schema",
                "runtime_fingerprint",
                "retained_oval_oval_witness_sha256",
                "sources",
                "added_files",
            }
            or codec["schema"] != "finite-oval-codec-test-transition-v1"
            or codec["retained_oval_oval_witness_sha256"] != OVAL_OVAL_WITNESS_SHA256
            or set(codec["sources"]) != {_OVAL_POINT_SOURCE}
            or set(codec["added_files"]) != {OVAL_CODEC_OWNER}
        ):
            raise SystemExit("Oval codec test transition membership differs.")
        _checked_bytes(root, _OVAL_POINT_SOURCE, codec["sources"][_OVAL_POINT_SOURCE])
        additions.update(_selection_members(codec["added_files"], root))
        runtime = codec["runtime_fingerprint"]
        raw += b"\0" + codec_raw
    fight_reroll = _stage2_fight_reroll_successor(root) if has_fight_reroll else None
    source_successors: SourceSuccessors = {}
    test_successors: TestSuccessors = {}
    fight_successor = _stage2_fight_successor(root) if has_stage2_fight else None
    stage2_fight_tests = {} if fight_successor is None else fight_successor[1]
    if has_gameplay_budget:
        if not has_codec:
            raise SystemExit("Gameplay movement budget tests require the oval codec predecessor.")
        runtime, source_successors, test_successors, successor_raw = _gameplay_budget_successor(
            root,
            current_tests=stage2_fight_tests,
            current_sources={} if fight_reroll is None else fight_reroll[3],
        )
        raw += b"\0" + successor_raw
    if fight_successor is not None:
        runtime, _, successor_raw = fight_successor
        raw += b"\0" + successor_raw
    counteroffensive_runtime = runtime
    melee_restore_tests = None
    melee_restore_raw = None
    if has_melee_restore:
        runtime, melee_restore_tests, melee_restore_raw = _stage2_melee_restore_successor(
            root, current_tests=None if fight_reroll is None else fight_reroll[1]
        )
    if fight_reroll is not None:
        runtime = fight_reroll[0]
    terminal_restore = _terminal_restore_successor(root) if has_terminal_restore else None
    if terminal_restore is not None:
        runtime = terminal_restore[0]
        # This successor changes runtime sources only. It uses the same
        # authenticated behavioral selection as the terminal restore build.
        authority_guard = root / "src/warhammer40k_core/engine/runtime_read_only.py"
        _selection_no_links(root, authority_guard)
        if authority_guard.exists():
            for name, digest in CAVALCADE_AUTHORITY_SOURCES.items():
                _checked_bytes(root, name, digest)
            runtime = CAVALCADE_AUTHORITY_RUNTIME
    shadow_path = root / ROUND_FIVE_SHADOW_TRANSITION
    _selection_no_links(root, shadow_path)
    shadow = None
    if shadow_path.exists():
        if runtime != CAVALCADE_AUTHORITY_RUNTIME:
            raise SystemExit("Round-five Shadow tests require the Cavalcade authority predecessor.")
        shadow = _round_five_shadow_successor(root, retained_cutover_sha256=retained_cutover_sha256)
        runtime = shadow[0]
    close_quarters_path = root / CLOSE_QUARTERS_TRANSITION
    _selection_no_links(root, close_quarters_path)
    close_quarters = None
    if close_quarters_path.exists():
        if shadow is None:
            raise SystemExit("Close Quarters tests require the Round-five Shadow predecessor.")
        close_quarters = _close_quarters_test_successor(
            root, retained_cutover_sha256=retained_cutover_sha256, predecessor_runtime=runtime
        )
        runtime = close_quarters[0]
    strict_replay_path = root / STRICT_REPLAY_TRANSITION
    _selection_no_links(root, strict_replay_path)
    strict_replay = None
    if strict_replay_path.exists():
        if close_quarters is None:
            raise SystemExit("Strict replay tests require the Close Quarters predecessor.")
        strict_replay = _strict_replay_test_successor(
            root, retained_cutover_sha256=retained_cutover_sha256, predecessor_runtime=runtime
        )
        runtime, _, _, strict_replay_sources = strict_replay
        if strict_replay_sources.keys() & source_successors.keys():
            raise SystemExit("Strict replay sources overlap the predecessor transition.")
        source_successors.update(strict_replay_sources)
    allocation_path = root / ALLOCATION_COHERENCY_ADDITION
    _selection_no_links(root, allocation_path)
    allocation_raw = None
    if allocation_path.exists():
        if strict_replay is None:
            raise SystemExit("Allocation coherency tests require the Strict Replay predecessor.")
        allocation_raw = _checked_bytes(
            root, ALLOCATION_COHERENCY_ADDITION, ALLOCATION_COHERENCY_SHA256
        )
        allocation = json.loads(allocation_raw, object_pairs_hook=_selection_object)
        if (
            allocation.keys()
            != {
                "schema",
                "retained_strict_replay_sha256",
                "retained_runtime_fingerprint",
                "runtime_fingerprint",
                "policy_sha256",
                "added_files",
            }
            or allocation["schema"] != "finite-stage2-allocation-coherency-test-addition-v1"
            or allocation["retained_strict_replay_sha256"] != STRICT_REPLAY_SHA256
            or allocation["retained_runtime_fingerprint"] != runtime
            or set(allocation["added_files"]) != {ALLOCATION_COHERENCY_OWNER}
        ):
            raise SystemExit("Allocation coherency test addition differs.")
        _checked_bytes(root, ALLOCATION_COHERENCY_POLICY, allocation["policy_sha256"])
        additions.update(_selection_members(allocation["added_files"], root))
        runtime = allocation["runtime_fingerprint"]
    cover_event_path = root / COVER_EVENT_IDENTITY_ADDITION
    _selection_no_links(root, cover_event_path)
    cover_event_raw = None
    if cover_event_path.exists():
        if allocation_raw is None:
            raise SystemExit(
                "Cover event identity tests require the allocation coherency predecessor."
            )
        cover_event_raw = _checked_bytes(
            root, COVER_EVENT_IDENTITY_ADDITION, COVER_EVENT_IDENTITY_SHA256
        )
        cover_event = json.loads(cover_event_raw, object_pairs_hook=_selection_object)
        if (
            cover_event.keys()
            != {
                "schema",
                "retained_allocation_coherency_sha256",
                "retained_runtime_fingerprint",
                "runtime_fingerprint",
                "source",
                "added_files",
            }
            or cover_event["schema"] != "finite-stage2-cover-event-identity-test-addition-v1"
            or cover_event["retained_allocation_coherency_sha256"] != ALLOCATION_COHERENCY_SHA256
            or cover_event["retained_runtime_fingerprint"] != runtime
            or set(cover_event["source"]) != {"before", "after"}
            or set(cover_event["added_files"]) != {COVER_EVENT_IDENTITY_OWNER}
        ):
            raise SystemExit("Cover event identity test addition differs.")
        _checked_bytes(root, COVER_EVENT_IDENTITY_SOURCE, cover_event["source"]["after"])
        additions.update(_selection_members(cover_event["added_files"], root))
        runtime = cover_event["runtime_fingerprint"]
    retained = _identity_test_transition(
        root,
        retained_cutover_sha256,
        runtime=runtime,
        source_successors=source_successors,
        test_successors=test_successors,
    )
    if retained is None:
        raise SystemExit(
            "Exact movement test transition requires the numerical identity predecessor."
        )
    updated, added, retained_raw = retained
    if additions.keys() & (updated.keys() | added.keys()):
        raise SystemExit("Exact movement test cases overlap the predecessor selection.")
    if test_successors:
        for name in (
            GAMEPLAY_BUDGET_OWNER,
            GAMEPLAY_CHARGE_OWNER,
            GAMEPLAY_ESCAPE_OWNER,
            GAMEPLAY_SORCERER_OWNER,
        ):
            updated[name] = test_successors[name]
    updated.update(stage2_fight_tests)
    if has_counteroffensive:
        tests, counteroffensive_raw = _counteroffensive_test_successor(
            root,
            counteroffensive_runtime,
            current_tests=melee_restore_tests if fight_reroll is None else fight_reroll[1],
        )
        if tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Stage 2 Counteroffensive tests overlap the predecessor selection.")
        updated.update(tests)
        raw += b"\0" + counteroffensive_raw
    if melee_restore_tests is not None and melee_restore_raw is not None:
        updated.update(melee_restore_tests)
        raw += b"\0" + melee_restore_raw
    if fight_reroll is not None:
        _, tests, reroll_raw, _ = fight_reroll
        updated.update(tests)
        raw += b"\0" + reroll_raw
    if terminal_restore is not None:
        _, tests, terminal_restore_raw = terminal_restore
        if tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Terminal restore tests overlap the predecessor selection.")
        updated.update(tests)
        raw += b"\0" + terminal_restore_raw
    if shadow is not None:
        _, tests, shadow_raw = shadow
        if tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Round-five Shadow tests overlap the predecessor selection.")
        updated.update(tests)
        raw += b"\0" + shadow_raw
    if close_quarters is not None:
        _, tests, close_quarters_raw = close_quarters
        if tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Close Quarters tests overlap the predecessor selection.")
        updated.update(tests)
        raw += b"\0" + close_quarters_raw
    if strict_replay is not None:
        _, tests, strict_replay_raw, _ = strict_replay
        if tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Strict replay tests overlap the predecessor selection.")
        updated.update(tests)
        raw += b"\0" + strict_replay_raw
    if allocation_raw is not None:
        raw += b"\0" + allocation_raw
    if cover_event_raw is not None:
        raw += b"\0" + cover_event_raw
    return updated, {**added, **additions}, retained_raw + b"\0" + raw


def _round_five_shadow_successor(
    root: Path, *, retained_cutover_sha256: str
) -> tuple[str, TestSuccessors, bytes]:
    raw = _checked_bytes(root, ROUND_FIVE_SHADOW_TRANSITION, ROUND_FIVE_SHADOW_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "test",
        }
        or record["schema"] != "finite-round-five-shadow-test-transition-v1"
        or record["base"] != ROUND_FIVE_SHADOW_BASE
        or record["retained_runtime_fingerprint"] != CAVALCADE_AUTHORITY_RUNTIME
        or set(record["sources"]) != set(ROUND_FIVE_SHADOW_SOURCES)
        or set(record["test"]) != {ROUND_FIVE_SHADOW_OWNER}
    ):
        raise SystemExit("Round-five Shadow test transition membership differs.")
    for name, change in record["sources"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit(
                "Round-five Shadow source transition requires exact before and after hashes."
            )
        _checked_bytes(root, name, change["after"])
    from scripts.build_test_shards import CUTOVER_PATH

    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    test = record["test"][ROUND_FIVE_SHADOW_OWNER]
    if (
        set(test) != {"before", "after"}
        or test["before"] != cutover["active_files"][ROUND_FIVE_SHADOW_OWNER]
    ):
        raise SystemExit("Round-five Shadow test predecessor differs.")
    members = _selection_members({ROUND_FIVE_SHADOW_OWNER: test["after"]}, root)
    return record["runtime_fingerprint"], members, raw


def _close_quarters_test_successor(
    root: Path, *, retained_cutover_sha256: str, predecessor_runtime: str
) -> tuple[str, TestSuccessors, bytes]:
    raw = _checked_bytes(root, CLOSE_QUARTERS_TRANSITION, CLOSE_QUARTERS_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_shadow_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "test",
        }
        or record["schema"] != "finite-close-quarters-test-transition-v1"
        or record["base"] != CLOSE_QUARTERS_BASE
        or record["retained_shadow_sha256"] != ROUND_FIVE_SHADOW_SHA256
        or record["retained_runtime_fingerprint"] != predecessor_runtime
        or set(record["sources"]) != set(CLOSE_QUARTERS_SOURCES)
        or set(record["test"]) != {CLOSE_QUARTERS_OWNER}
    ):
        raise SystemExit("Close Quarters test transition membership differs.")
    for name, change in record["sources"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit(
                "Close Quarters source transition requires exact before and after hashes."
            )
        _checked_bytes(root, name, change["after"])
    from scripts.build_test_shards import CUTOVER_PATH

    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    test = record["test"][CLOSE_QUARTERS_OWNER]
    if (
        set(test) != {"before", "after"}
        or test["before"] != cutover["active_files"][CLOSE_QUARTERS_OWNER]
    ):
        raise SystemExit("Close Quarters test predecessor differs.")
    members = _selection_members({CLOSE_QUARTERS_OWNER: test["after"]}, root)
    return record["runtime_fingerprint"], members, raw


def _strict_replay_test_successor(
    root: Path, *, retained_cutover_sha256: str, predecessor_runtime: str
) -> tuple[str, TestSuccessors, bytes, SourceSuccessors]:
    raw = _checked_bytes(root, STRICT_REPLAY_TRANSITION, STRICT_REPLAY_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_close_quarters_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "test",
        }
        or record["schema"] != "finite-stage2-strict-replay-test-transition-v1"
        or record["base"] != STRICT_REPLAY_BASE
        or record["retained_close_quarters_sha256"] != CLOSE_QUARTERS_SHA256
        or record["retained_runtime_fingerprint"] != predecessor_runtime
        or set(record["sources"]) != set(STRICT_REPLAY_SOURCES)
        or set(record["test"]) != {STRICT_REPLAY_OWNER}
    ):
        raise SystemExit("Strict replay test transition membership differs.")
    for name, change in record["sources"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit(
                "Strict replay source transition requires exact before and after hashes."
            )
        _checked_bytes(root, name, change["after"])
    from scripts.build_test_shards import CUTOVER_PATH

    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    test = record["test"][STRICT_REPLAY_OWNER]
    if (
        set(test) != {"before", "after"}
        or test["before"] != cutover["active_files"][STRICT_REPLAY_OWNER]
    ):
        raise SystemExit("Strict replay test predecessor differs.")
    members = _selection_members({STRICT_REPLAY_OWNER: test["after"]}, root)
    return record["runtime_fingerprint"], members, raw, record["sources"]


def _identity_test_transition(
    root: Path,
    retained_cutover_sha256: str,
    *,
    runtime: str,
    source_successors: SourceSuccessors | None = None,
    test_successors: TestSuccessors | None = None,
) -> TestTransition | None:
    sources = {} if source_successors is None else source_successors
    tests = {} if test_successors is None else test_successors
    for name in (ADDITION, MANIFEST, SOURCE, OWNER):
        _selection_no_links(root, root / name)
    manifest = (
        json.loads((root / MANIFEST).read_bytes(), object_pairs_hook=_selection_object)
        if (root / MANIFEST).is_file()
        else None
    )
    fingerprint = manifest.get("fingerprint") if isinstance(manifest, dict) else None
    if (
        not any((root / name).exists() for name in (ADDITION, SOURCE, OWNER))
        and fingerprint != runtime
    ):
        return None
    if retained_cutover_sha256 != RETAINED_CUTOVER_SHA256 or fingerprint != runtime:
        raise SystemExit(
            "Numerical identity test transition requires its retained cutover and runtime."
        )
    raw = _checked_bytes(root, ADDITION, ADDITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record
        != {
            "schema": "finite-engine-numerical-identity-test-transition-v1",
            "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
            "retained_foundation_sha256": FOUNDATION_SHA256,
            "retained_profile_sha256": PROFILE_SHA256,
            "retained_symbolic_sha256": SYMBOLIC_SHA256,
            "retained_polygon_sha256": POLYGON_SHA256,
            "retained_circle_sha256": CIRCLE_SHA256,
            "retained_queries_sha256": QUERIES_ADDITION_SHA256,
            "retained_pairs_sha256": PAIRS_ADDITION_SHA256,
            "retained_contact_sha256": CONTACT_ADDITION_SHA256,
            "runtime_fingerprint": RUNTIME,
            "sources": record["sources"],
            "added_files": record["added_files"],
            "added_cases": record["added_cases"],
            "case_id_successors": record["case_id_successors"],
            "updated_files": record["updated_files"],
        }
        or set(record["added_files"]) != {OWNER}
        or set(record["updated_files"])
        != {
            "tests/rules/section18/test_facade.py",
            "tests/infrastructure/adapters/unit/test_linux_authority.py",
            "tests/infrastructure/adapters/test_canonical_deployment_coverage.py",
        }
    ):
        raise SystemExit("Numerical identity test transition membership differs.")
    for name, digest in record["sources"].items():
        _retained_source(root, name, digest, sources)
    contact_raw = _checked_bytes(root, CONTACT_ADDITION, CONTACT_ADDITION_SHA256)
    contact = json.loads(contact_raw, object_pairs_hook=_selection_object)
    for name, digest in contact["sources"].items():
        _retained_source(root, name, digest, sources)
    pairs_raw = _checked_bytes(root, PAIRS_ADDITION, PAIRS_ADDITION_SHA256)
    pairs = json.loads(pairs_raw, object_pairs_hook=_selection_object)
    for name, digest in pairs["sources"].items():
        _retained_source(root, name, digest, sources)
    queries_raw = _checked_bytes(root, QUERIES_ADDITION, QUERIES_ADDITION_SHA256)
    queries = json.loads(queries_raw, object_pairs_hook=_selection_object)
    # The hash-pinned original transition retains its original point-query source.
    # Only this successor admits the exact private annotation change.
    if pairs["sources"][QUERIES] != QUERIES_SHA256:
        raise SystemExit("Unreviewed point-query internal annotation successor.")
    foundation_raw = _checked_bytes(root, FOUNDATION_ADDITION, FOUNDATION_SHA256)
    profile_raw = _checked_bytes(root, PROFILE_ADDITION, PROFILE_SHA256)
    _checked_bytes(root, FOUNDATION_SOURCE, FOUNDATION_SOURCE_SHA256)
    foundation = json.loads(foundation_raw, object_pairs_hook=_selection_object)
    profile = json.loads(profile_raw, object_pairs_hook=_selection_object)
    symbolic_raw = _checked_bytes(root, SYMBOLIC_ADDITION, SYMBOLIC_SHA256)
    symbolic = json.loads(symbolic_raw, object_pairs_hook=_selection_object)
    polygon_raw = _checked_bytes(root, POLYGON_ADDITION, POLYGON_SHA256)
    polygon = json.loads(polygon_raw, object_pairs_hook=_selection_object)
    circle_raw = _checked_bytes(root, CIRCLE_ADDITION, CIRCLE_SHA256)
    circle = json.loads(circle_raw, object_pairs_hook=_selection_object)
    for name, digest in circle["sources"].items():
        _retained_source(root, name, digest, sources)
    for name, digest in polygon["sources"].items():
        _retained_source(root, name, digest, sources)
    for name, digest in symbolic["sources"].items():
        _retained_source(root, name, digest, sources)
    for name, digest in profile["sources"].items():
        _retained_source(root, name, record["sources"].get(name, digest), sources)
    current_updated = _selection_members(record["updated_files"], root, current=tests)
    current_updated = {name: tests.get(name, row) for name, row in current_updated.items()}
    updated = _selection_members(profile["updated_files"], root, current=current_updated)
    from scripts.speedup_test_admission import ADDITION as SPEEDUP_ADDITION
    from scripts.speedup_test_admission import ADDITION_SHA256 as SPEEDUP_SHA256

    speedup_raw = _checked_bytes(root, SPEEDUP_ADDITION, SPEEDUP_SHA256)
    speedup = json.loads(speedup_raw, object_pairs_hook=_selection_object)
    if speedup != {
        "schema": "finite-speedup-test-transition-v1",
        "retained_cutover_sha256": RETAINED_CUTOVER_SHA256,
        "retained_exact_contact_sha256": CONTACT_ADDITION_SHA256,
        "runtime_fingerprint": contact["runtime_fingerprint"],
        "updated_files": speedup["updated_files"],
    }:
        raise SystemExit("Numerical identity predecessor speedup metadata differs.")
    updated.update(_selection_members(speedup["updated_files"], root, current=current_updated))
    updated.update(current_updated)
    retained = _selection_members(foundation["added_files"], root)
    retained.update(_selection_members(profile["added_files"], root, current=tests))
    retained.update(_selection_members(symbolic["added_files"], root))
    retained.update(_selection_members(polygon["added_files"], root))
    retained.update(_selection_members(circle["added_files"], root))
    retained.update(_selection_members(queries["added_files"], root))
    retained.update(_selection_members(pairs["added_files"], root))
    retained.update(_selection_members(contact["added_files"], root))
    additions = _selection_members(record["added_files"], root, current=tests)
    if additions.keys() & (updated.keys() | retained.keys()):
        raise SystemExit("Numerical identity test transition source memberships overlap.")
    return (
        updated,
        {name: tests.get(name, row) for name, row in (retained | additions).items()},
        foundation_raw
        + b"\0"
        + profile_raw
        + b"\0"
        + symbolic_raw
        + b"\0"
        + polygon_raw
        + b"\0"
        + circle_raw
        + b"\0"
        + queries_raw
        + b"\0"
        + pairs_raw
        + b"\0"
        + contact_raw
        + b"\0"
        + speedup_raw
        + b"\0"
        + raw,
    )
