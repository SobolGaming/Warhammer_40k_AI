"""Finite numerical-identity source admission over the retained speedup transition."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypedDict, cast

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


OPENING_SHADOW_FORM_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-opening-shadow-form-test-transition-v1.json"
)
OPENING_SHADOW_FORM_SHA256 = "a69c8069b46b70ef3e9afe0bea2c16f54d2d152fe9dbf72fcaa70951ff58b9d0"
OPENING_SHADOW_FORM_BASE = "a7752da914356a43c144b8b4ea1dfd522cd0c0c5"
OPENING_SHADOW_FORM_POLICY = "src/warhammer40k_core/ai/opening_shadow_form.py"
OPENING_SHADOW_FORM_OWNER = (
    "tests/factions/chaos_daemons/integration/test_cavalcade_native_screen_prefix.py"
)


OPENING_MOVEMENT_UNIT_ADDITION = (
    "data/source_audits/ci64_provenance_v1/stage2-opening-movement-unit-test-addition-v1.json"
)
OPENING_MOVEMENT_UNIT_SHA256 = "6c821e5ea1fe9933539d8b63d63bc1d3777766b68581e66ae664fc76caebf15e"
OPENING_MOVEMENT_UNIT_POLICY = "src/warhammer40k_core/ai/opening_movement_unit.py"
OPENING_MOVEMENT_UNIT_OWNER = (
    "tests/factions/chaos_daemons/integration/test_cavalcade_opening_movement_unit.py"
)


MONSTER_MASH_ADDITION = (
    "data/source_audits/ci64_provenance_v1/monster-mash-v995-test-addition-v1.json"
)
MONSTER_MASH_SHA256 = "2f17e1f6876138c519d6c15d9eb5729275b19b0be0ee9d89ecb60be6fd2c0f84"
MONSTER_MASH_OWNER = "tests/factions/chaos_daemons/integration/test_monster_mash_v995_roster.py"
MONSTER_MASH_SOURCES = (
    "data/army_lists/monster-mash.json",
    "tests/support/monster_mash_v995.py",
    (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "chaos_daemons_monster_mash_2026_11/__init__.py"
    ),
    (
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "chaos_daemons_monster_mash_2026_11/artifacts/catalog.json"
    ),
)


SHOOTING_VISIBILITY_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/monster-mash-shooting-visibility-test-transition-v1.json"
)
SHOOTING_VISIBILITY_SHA256 = "4cdd4f407bd7e96e0f3ca446bc5faa005eb49ded60e9b409fe4a6bc06b3da631"
SHOOTING_VISIBILITY_BASE = "d1af6721e1f544898ce25ef7fdd611110b31b6fc"
SHOOTING_VISIBILITY_SOURCE = "src/warhammer40k_core/geometry/visibility_witnesses.py"


MONSTER_MASH_ATTACK_REROLL_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/monster-mash-attack-reroll-test-transition-v1.json"
)
MONSTER_MASH_ATTACK_REROLL_SHA256 = (
    "27bc3311f7f63b94ab566a377c37648b89dd666422a6e8c000c09068243f9ea5"
)
MONSTER_MASH_ATTACK_REROLL_BASE = "0b8eb690cc0b5e3b724c3e3e8fb754f72fcc6330"
MONSTER_MASH_ATTACK_REROLL_OWNERS = (
    "tests/rules/section04/test_facade.py",
    "tests/rules/section04/test_fight_facade.py",
)
MONSTER_MASH_ATTACK_REROLL_SOURCES = (
    "src/warhammer40k_core/engine/command_reroll_windows.py",
    "src/warhammer40k_core/engine/critical_wounds.py",
    STAGE2_FIGHT_REROLL_SOURCE,
    "src/warhammer40k_core/engine/rule_trigger_runtime.py",
)


ROUND4_BATTLE_SHOCK_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/monster-mash-round4-battle-shock-test-transition-v1.json"
)
ROUND4_BATTLE_SHOCK_SHA256 = "88eca67f3513357bad3f35bb68fe8d3607e374f360485dd4c3ca3c06b0a7eaf3"
ROUND4_BATTLE_SHOCK_BASE = "1629879b409fbbd29addf062abd30359ca923986"
ROUND4_BATTLE_SHOCK_OWNER = "tests/factions/chaos_daemons/unit/test_chaos_daemons_army_rule.py"
ROUND4_BATTLE_SHOCK_TERRITORY_SOURCE = (
    "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
    "chaos_daemons/battle_shock_territory_authority.py"
)
ROUND4_BATTLE_SHOCK_SOURCES = (
    "src/warhammer40k_core/engine/battle_shock_historical_authority.py",
    "src/warhammer40k_core/engine/catalog_unit_move_completed_battle_shock_runtime.py",
    ROUND_FIVE_SHADOW_SOURCES[0],
    "src/warhammer40k_core/engine/generic_effect_history.py",
    ROUND4_BATTLE_SHOCK_TERRITORY_SOURCE,
)


ROUND4_MALICE_BEARER_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/"
    "monster-mash-round4-malice-bearer-test-transition-v1.json"
)
ROUND4_MALICE_BEARER_SHA256 = "61b11c5be2d8c47a84d0155e555ee600bdb5f6439676152cffb53a4e19c42ae1"
ROUND4_MALICE_BEARER_BASE = "fb84de924d1e105d68321075d9eee5f705878a62"
ROUND4_MALICE_BEARER_SOURCE = (
    "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
    "chaos_daemons/detachments/shadow_legion/fight_sequencing.py"
)
ROUND4_MALICE_BEARER_OWNER = (
    "tests/factions/chaos_daemons/unit/test_generic_rule_ability_registry.py"
)


ROUND3_SHALAXI_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/monster-mash-round3-shalaxi-test-transition-v1.json"
)
ROUND3_SHALAXI_SHA256 = "a9e2413b2d06ece74221a364cbcaa17525e7995100b725517f31902c7a1edf43"
ROUND3_SHALAXI_BASE = "1e5d53a3a8a09eac3752073ed0fd7d3247789248"
ROUND3_SHALAXI_SOURCES = (
    "src/warhammer40k_core/geometry/continuous_visibility.py",
    "src/warhammer40k_core/geometry/visibility_axis_shadow.py",
    "src/warhammer40k_core/geometry/visibility_certificates.py",
    "src/warhammer40k_core/geometry/visibility_witnesses.py",
)


GROUND_CHARGE_TEST_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/stage2-ground-charge-test-addition-v1.json"
)


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
    root: Path,
    *,
    current_tests: TestSuccessors | None,
    current_sources: SourceSuccessors,
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
        _retained_source(root, name, change["after"], current_sources)
    tests = _selection_members(
        {name: row["after"] for name, row in record["test"].items()},
        root,
        current=current_tests,
    )
    return record["runtime_fingerprint"], tests, raw


def _stage2_fight_reroll_successor(
    root: Path,
    *,
    current_sources: SourceSuccessors,
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
        _retained_source(root, name, change["after"], current_sources)
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


def _pending_battle_shock_source_transition(
    root: Path,
) -> tuple[str, str, SourceSuccessors, bytes] | None:
    name = "data/source_audits/ci64_provenance_v1/stage2-pending-battle-shock-transition-v1.json"
    path = root / name
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(
        root, name, "1188532c9acbc0b9c4b19323e98458aeb64d7d51ad3c8bf3b889486230568a03"
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_screen_movement_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
        }
        or record["schema"] != "finite-stage2-pending-battle-shock-transition-v1"
        or record["base"] != "161378a16c4557228b2af45db0d311a522eb3f8f"
        or record["retained_screen_movement_sha256"]
        != "7e0b32cb0f7a0ef8e7d05f9b0a4aa7bb965cb6644e5d42ffd035897a536deb94"
    ):
        raise SystemExit("Pending Battle-shock source transition differs.")
    expected_sources = {
        path
        for path in CAVALCADE_AUTHORITY_SOURCES
        if path.endswith(("battle_shock_hooks.py", "battle_shock_outcome_authority.py"))
    } | {
        ROUND_FIVE_SHADOW_SOURCES[0],
        "src/warhammer40k_core/engine/faction_content/pending_battle_shock_routes.py",
    }
    sources: SourceSuccessors = record["sources"]
    if sources.keys() != expected_sources:
        raise SystemExit("Pending Battle-shock source transition membership differs.")
    for source, change in sources.items():
        if change.keys() != {"before", "after"}:
            raise SystemExit("Pending Battle-shock transition requires exact source digests.")
        _checked_bytes(root, source, change["after"])
    return record["retained_runtime_fingerprint"], record["runtime_fingerprint"], sources, raw


def _grotesque_regeneration_test_successor(
    root: Path, *, previous_runtime: str, previous_transition: bytes
) -> tuple[str, TestSuccessors, bytes] | None:
    from scripts.build_test_shards import CUTOVER_PATH

    name = "data/source_audits/ci64_provenance_v1/grotesque-regeneration-transition-v1.json"
    path = root / name
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(
        root, name, "4e48442b32a20933c864a1f5e7c5d398233526c9d1d4a4aa720f0eb50af86581"
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    owner = "tests/rules/section02/test_02_02_04_healing.py"
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, RETAINED_CUTOVER_SHA256),
        object_pairs_hook=_selection_object,
    )
    if (
        set(record)
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "test",
        }
        or record["schema"] != "finite-grotesque-regeneration-transition-v1"
        or record["base"] != "d9185cf53a2816ab666f3c1b16410b960a3d1cc7"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or set(record["test"]) != {"before", "after"}
        or record["test"]["before"] != cutover["active_files"][owner]
    ):
        raise SystemExit("Grotesque Regeneration test transition differs.")
    for source, digest in record["sources"].items():
        _checked_bytes(root, source, digest)
    tests = _selection_members({owner: record["test"]["after"]}, root)
    return record["runtime_fingerprint"], tests, raw


BLOOD_BEGETS_SKULLS_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/blood-begets-skulls-transition-v1.json"
)
BLOOD_BEGETS_SKULLS_TRANSITION_SHA256 = (
    "60b75729404329a6d013b8b3cdd9e08527294ea2da50cfad43549473cf08dccf"
)
BLOOD_BEGETS_SKULLS_OWNER = "tests/factions/chaos_daemons/integration/test_blood_begets_skulls.py"


SKULLS_BEGET_BLOOD_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/skulls-beget-blood-transition-v1.json"
)
SKULLS_BEGET_BLOOD_TRANSITION_SHA256 = (
    "d52df25433449b126bdd6549b9b687a7105a0bc1737645357c7b73fce40c8d95"
)
SKULLS_BEGET_BLOOD_OWNER = "tests/factions/chaos_daemons/integration/test_skulls_beget_blood.py"
WRATH_UNDENIABLE_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/wrath-undeniable-transition-v1.json"
)
WRATH_UNDENIABLE_TRANSITION_SHA256 = (
    "16917990831b5c2a30720e21fd6decde891b7b8aca883439ec21038538142d29"
)
WRATH_UNDENIABLE_OWNER = "tests/factions/chaos_daemons/integration/test_wrath_undeniable.py"

GORE_HUNGRY_ONSLAUGHT_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/gore-hungry-onslaught-transition-v1.json"
)
GORE_HUNGRY_ONSLAUGHT_SHA256 = "6f854ba2aad31c2ff3d84343151692174d492356cac79afeed1c6105a2f72ead"
GORE_HUNGRY_ONSLAUGHT_OWNER = (
    "tests/factions/chaos_daemons/integration/test_gore_hungry_onslaught.py"
)
GORE_HUNGRY_ONSLAUGHT_REPLACED_SOURCES = {
    "src/warhammer40k_core/engine/charge_preselection_stratagems.py",
    "src/warhammer40k_core/engine/faction_content/warhammer_40000_11th/"
    "chaos_daemons/detachments/blood_legion/stratagems.py",
    "src/warhammer40k_core/engine/stratagems_eligibility.py",
    "src/warhammer40k_core/engine/stratagems_model.py",
    "src/warhammer40k_core/engine/stratagems_requests.py",
    "src/warhammer40k_core/engine/stratagems_targeting.py",
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "faction_blood_legion_ir_support_2026_27.py",
}
GORE_HUNGRY_ONSLAUGHT_NEW_SOURCES = {
    "src/warhammer40k_core/engine/charge_roll_flow.py",
    "src/warhammer40k_core/engine/movement_legality.py",
    "src/warhammer40k_core/engine/phases/movement_action_decisions.py",
    "src/warhammer40k_core/engine/phases/movement_handler.py",
    "src/warhammer40k_core/engine/phases/movement_start_actions.py",
    "src/warhammer40k_core/engine/unit_rule_effects.py",
}
_GORE_HUNGRY_ONSLAUGHT_BUDGET_SOURCE = (
    "src/warhammer40k_core/engine/phases/movement_resolution_flow.py"
)
_GORE_HUNGRY_ONSLAUGHT_IDENTITY_SOURCE = "src/warhammer40k_core/geometry/pathing.py"
GORE_HUNGRY_ONSLAUGHT_HISTORICAL_SOURCES = {
    _GORE_HUNGRY_ONSLAUGHT_BUDGET_SOURCE,
    _GORE_HUNGRY_ONSLAUGHT_IDENTITY_SOURCE,
}


class _GoreOnslaughtTestBinding(TypedDict):
    before: dict[str, object]
    after: dict[str, object]


class _GoreOnslaughtTransition(TypedDict):
    schema: str
    base: str
    retained_transition_sha256: str
    retained_runtime_fingerprint: str
    runtime_fingerprint: str
    replaced_sources: SourceSuccessors
    new_sources: dict[str, str]
    historical_sources: SourceSuccessors
    updated_files: dict[str, _GoreOnslaughtTestBinding]
    added_files: TestSuccessors


def _gore_hungry_onslaught_transition(root: Path) -> tuple[_GoreOnslaughtTransition, bytes] | None:
    path = root / GORE_HUNGRY_ONSLAUGHT_TRANSITION
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, GORE_HUNGRY_ONSLAUGHT_TRANSITION, GORE_HUNGRY_ONSLAUGHT_SHA256)
    record = cast(_GoreOnslaughtTransition, json.loads(raw, object_pairs_hook=_selection_object))
    classifier = "tests/infrastructure/source_governance/unit/test_blocked_row_classification.py"
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "replaced_sources",
            "new_sources",
            "historical_sources",
            "updated_files",
            "added_files",
        }
        or record["schema"] != "finite-gore-hungry-onslaught-transition-v1"
        or record["base"] != "f69eda2040ab55db4dd18686eee69edafcca9dd2"
        or record["replaced_sources"].keys() != GORE_HUNGRY_ONSLAUGHT_REPLACED_SOURCES
        or record["new_sources"].keys() != GORE_HUNGRY_ONSLAUGHT_NEW_SOURCES
        or record["historical_sources"].keys() != GORE_HUNGRY_ONSLAUGHT_HISTORICAL_SOURCES
        or record["added_files"].keys() != {GORE_HUNGRY_ONSLAUGHT_OWNER}
        or record["updated_files"].keys()
        != {BLOOD_BEGETS_SKULLS_OWNER, SKULLS_BEGET_BLOOD_OWNER, classifier}
        or any(
            binding.keys() != {"before", "after"} for binding in record["updated_files"].values()
        )
    ):
        raise SystemExit("Gore-Hungry Onslaught test transition differs.")
    for source, binding in record["historical_sources"].items():
        if binding.keys() != {"before", "after"} or binding["before"] == binding["after"]:
            raise SystemExit("Gore-Hungry Onslaught historical source binding differs: " + source)
        _checked_bytes(root, source, binding["after"])
    return record, raw


def _skulls_beget_blood_test_successor(
    root: Path,
    *,
    previous: dict[str, object],
    previous_runtime: str,
    previous_transition: bytes,
    previous_sources: dict[str, str],
    retained_additions: TestSuccessors,
) -> tuple[str, TestSuccessors, TestSuccessors, bytes]:
    raw = _checked_bytes(root, SKULLS_BEGET_BLOOD_TRANSITION, SKULLS_BEGET_BLOOD_TRANSITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    classifier = "tests/infrastructure/source_governance/unit/test_blocked_row_classification.py"
    previous_updated = previous["updated_files"]
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "replaced_sources",
            "new_sources",
            "added_files",
            "updated_files",
        }
        or record["schema"] != "finite-skulls-beget-blood-transition-v1"
        or record["base"] != "16069416ea8de4c5623402c1cc6d53e55b673cb0"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["added_files"].keys() != {SKULLS_BEGET_BLOOD_OWNER}
        or record["updated_files"].keys() != {classifier}
        or record["updated_files"][classifier].keys() != {"before", "after"}
        or not isinstance(previous_updated, dict)
        or record["updated_files"][classifier]["before"] != previous_updated[classifier]["after"]
    ):
        raise SystemExit("Skulls Beget Blood test transition differs.")
    replaced = record["replaced_sources"]
    new = record["new_sources"]
    if not replaced.keys() <= previous_sources.keys() or new.keys() & previous_sources.keys():
        raise SystemExit("Skulls Beget Blood source successor inventory differs.")
    current_sources = dict(previous_sources)
    for source, binding in replaced.items():
        if binding.keys() != {"before", "after"} or binding["before"] != previous_sources[source]:
            raise SystemExit("Skulls Beget Blood source predecessor differs: " + source)
        current_sources[source] = binding["after"]
    current_sources.update(new)
    members = record["added_files"]
    gore = _gore_hungry_onslaught_transition(root)
    if gore is not None:
        updated_test = gore[0]["updated_files"][SKULLS_BEGET_BLOOD_OWNER]
        if updated_test["before"] != members[SKULLS_BEGET_BLOOD_OWNER]:
            raise SystemExit("Gore-Hungry Onslaught Shooting test owner preimage differs.")
        members = {SKULLS_BEGET_BLOOD_OWNER: updated_test["after"]}
    added = _selection_members(members, root)
    if added.keys() & retained_additions.keys():
        raise SystemExit("Skulls Beget Blood duplicates a retained test owner.")
    additions = {**retained_additions, **added}
    successor_path = root / WRATH_UNDENIABLE_TRANSITION
    _selection_no_links(root, successor_path)
    if successor_path.exists():
        predecessor = previous_transition + b"\0" + raw
        flight = _stage3_flight_normal_move_successor(
            root, previous_runtime=record["runtime_fingerprint"], previous_transition=predecessor
        )
        if flight is None:
            raise SystemExit("Wrath Undeniable requires the exact Stage 3 Flight predecessor.")
        flight_runtime, flight_tests, flight_raw = flight
        if flight_tests.keys() & (additions.keys() | {classifier}):
            raise SystemExit("Stage 3 flight Normal Move tests overlap the predecessor selection.")
        fingerprint, updated, additions, successor_raw = _wrath_undeniable_test_successor(
            root,
            previous=record,
            predecessor=predecessor + b"\0" + flight_raw,
            previous_runtime=flight_runtime,
            previous_sources=current_sources,
            previous_additions={**additions, **flight_tests},
            classifier=classifier,
        )
        return fingerprint, updated, additions, b"\0".join((raw, flight_raw, successor_raw))
    for source, digest in current_sources.items():
        _checked_bytes(root, source, digest)
    updated = _selection_members({classifier: record["updated_files"][classifier]["after"]}, root)
    return record["runtime_fingerprint"], updated, additions, raw


def _wrath_undeniable_test_successor(
    root: Path,
    *,
    previous: dict[str, object],
    predecessor: bytes,
    previous_runtime: str,
    previous_sources: dict[str, str],
    previous_additions: TestSuccessors,
    classifier: str,
) -> tuple[str, TestSuccessors, TestSuccessors, bytes]:
    raw = _checked_bytes(root, WRATH_UNDENIABLE_TRANSITION, WRATH_UNDENIABLE_TRANSITION_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    previous_updated = previous["updated_files"]
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "replaced_sources",
            "new_sources",
            "added_files",
            "updated_files",
        }
        or record["schema"] != "finite-wrath-undeniable-transition-v1"
        or record["base"] != "bdc1b2111530576a71bf3391564d5a9e9c356be0"
        or record["retained_transition_sha256"] != hashlib.sha256(predecessor).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["added_files"].keys() != {WRATH_UNDENIABLE_OWNER}
        or record["updated_files"].keys() != {classifier}
        or record["updated_files"][classifier].keys() != {"before", "after"}
        or not isinstance(previous_updated, dict)
        or record["updated_files"][classifier]["before"] != previous_updated[classifier]["after"]
    ):
        raise SystemExit("Wrath Undeniable test transition differs.")
    replaced = record["replaced_sources"]
    new = record["new_sources"]
    if not replaced.keys() <= previous_sources.keys() or new.keys() & previous_sources.keys():
        raise SystemExit("Wrath Undeniable source successor inventory differs.")
    current_sources = {**previous_sources, **new}
    for source, binding in replaced.items():
        if binding.keys() != {"before", "after"} or binding["before"] != previous_sources[source]:
            raise SystemExit("Wrath Undeniable source predecessor differs: " + source)
        current_sources[source] = binding["after"]
    added = _selection_members(record["added_files"], root)
    if added.keys() & previous_additions.keys():
        raise SystemExit("Wrath Undeniable duplicates a retained test owner.")
    classification = record["updated_files"][classifier]["after"]
    gore = _gore_hungry_onslaught_transition(root)
    if gore is not None:
        successor, _ = gore
        if (
            successor["updated_files"][classifier]["before"] != classification
            or not successor["replaced_sources"].keys() <= current_sources.keys()
            or successor["new_sources"].keys() & current_sources.keys()
        ):
            raise SystemExit("Gore-Hungry Onslaught test predecessor differs.")
        for source, binding in successor["replaced_sources"].items():
            if (
                binding.keys() != {"before", "after"}
                or binding["before"] != current_sources[source]
            ):
                raise SystemExit("Gore-Hungry Onslaught source predecessor differs: " + source)
            current_sources[source] = binding["after"]
        current_sources.update(successor["new_sources"])
        classification = successor["updated_files"][classifier]["after"]
    from scripts.fools_flight_test_admission import load_fools_flight_admission

    fools_flight = load_fools_flight_admission(root)
    if fools_flight is not None:
        current_sources, classification = fools_flight.replace_pins(
            sources=current_sources, classification=classification
        )
    for source, digest in current_sources.items():
        _checked_bytes(root, source, digest)
    updated = _selection_members({classifier: classification}, root)
    return record["runtime_fingerprint"], updated, {**previous_additions, **added}, raw


def _blood_begets_skulls_test_successor(
    root: Path,
    *,
    previous_runtime: str,
    previous_transition: bytes,
    previous_sources: dict[str, str],
    previous_classification: object,
    brass_additions: TestSuccessors,
) -> tuple[str, TestSuccessors, TestSuccessors, bytes]:
    raw = _checked_bytes(
        root, BLOOD_BEGETS_SKULLS_TRANSITION, BLOOD_BEGETS_SKULLS_TRANSITION_SHA256
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    classification_owner = (
        "tests/infrastructure/source_governance/unit/test_blocked_row_classification.py"
    )
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "replaced_sources",
            "new_sources",
            "added_files",
            "updated_files",
        }
        or record["schema"] != "finite-blood-begets-skulls-transition-v1"
        or record["base"] != "c63a300c28fa772f59c75b66d50038e5e6241cd5"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["added_files"].keys() != {BLOOD_BEGETS_SKULLS_OWNER}
        or record["updated_files"].keys() != {classification_owner}
        or record["updated_files"][classification_owner].keys() != {"before", "after"}
        or record["updated_files"][classification_owner]["before"] != previous_classification
    ):
        raise SystemExit("Blood Begets Skulls test transition differs.")
    replaced = record["replaced_sources"]
    if (
        not replaced.keys() <= previous_sources.keys()
        or record["new_sources"].keys() & previous_sources.keys()
    ):
        raise SystemExit("Blood Begets Skulls source successor inventory differs.")
    current_sources = dict(previous_sources)
    for source, binding in replaced.items():
        if binding.keys() != {"before", "after"} or binding["before"] != previous_sources[source]:
            raise SystemExit("Blood Begets Skulls source predecessor differs: " + source)
        current_sources[source] = binding["after"]
    current_sources.update(record["new_sources"])
    members = record["added_files"]
    gore = _gore_hungry_onslaught_transition(root)
    if gore is not None:
        updated_test = gore[0]["updated_files"][BLOOD_BEGETS_SKULLS_OWNER]
        if updated_test["before"] != members[BLOOD_BEGETS_SKULLS_OWNER]:
            raise SystemExit("Gore-Hungry Onslaught test owner preimage differs.")
        members = {BLOOD_BEGETS_SKULLS_OWNER: updated_test["after"]}
    added = _selection_members(members, root)
    if added.keys() & brass_additions.keys():
        raise SystemExit("Blood Begets Skulls duplicates a Sheathed in Brass test owner.")
    retained_runtime = record["runtime_fingerprint"]
    retained_transition = previous_transition + b"\0" + raw
    retained_additions = {**brass_additions, **added}
    stage3 = _stage3_melee_profile_successor(
        root, previous_runtime=retained_runtime, previous_transition=retained_transition
    )
    if stage3 is not None:
        retained_runtime, stage3_tests, stage3_raw = stage3
        if stage3_tests.keys() & (retained_additions.keys() | {classification_owner}):
            raise SystemExit("Stage 3 melee profile tests overlap the predecessor selection.")
        retained_additions.update(stage3_tests)
        retained_transition += b"\0" + stage3_raw
    successor_path = root / SKULLS_BEGET_BLOOD_TRANSITION
    _selection_no_links(root, successor_path)
    if successor_path.exists():
        if stage3 is None:
            raise SystemExit("Skulls Beget Blood requires the exact Stage 3 melee predecessor.")
        fingerprint, updated, additions, successor_raw = _skulls_beget_blood_test_successor(
            root,
            previous=record,
            previous_runtime=retained_runtime,
            previous_transition=retained_transition,
            previous_sources=current_sources,
            retained_additions=retained_additions,
        )
        return fingerprint, updated, additions, retained_transition + b"\0" + successor_raw
    for source, digest in current_sources.items():
        _checked_bytes(root, source, digest)
    updated = _selection_members(
        {classification_owner: record["updated_files"][classification_owner]["after"]}, root
    )
    return retained_runtime, updated, retained_additions, retained_transition


def _sheathed_in_brass_test_addition(
    root: Path, *, previous_runtime: str, previous_transition: bytes
) -> tuple[str, TestSuccessors, TestSuccessors, bytes] | None:
    from scripts.build_test_shards import CUTOVER_PATH

    name = "data/source_audits/ci64_provenance_v1/sheathed-in-brass-transition-v1.json"
    path = root / name
    _selection_no_links(root, path)
    if not path.exists():
        return None
    digest = "eed47b44cae336c88c37fbde89a41f8f7b0224e63945ffd75526170bd0bb6a66"
    raw = _checked_bytes(root, name, digest)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    owner = "tests/factions/chaos_daemons/integration/test_sheathed_in_brass.py"
    classification_owner = (
        "tests/infrastructure/source_governance/unit/test_blocked_row_classification.py"
    )
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, RETAINED_CUTOVER_SHA256),
        object_pairs_hook=_selection_object,
    )
    if (
        set(record)
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "added_files",
            "updated_files",
        }
        or record["schema"] != "finite-sheathed-in-brass-transition-v1"
        or record["base"] != "d137b5cc0c7557c8b6653a1aa36ee47260242945"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["added_files"].keys() != {owner}
        or record["updated_files"].keys() != {classification_owner}
        or record["updated_files"][classification_owner].keys() != {"before", "after"}
        or record["updated_files"][classification_owner]["before"]
        != cutover["active_files"][classification_owner]
    ):
        raise SystemExit("Sheathed in Brass test transition differs.")
    successor_path = root / BLOOD_BEGETS_SKULLS_TRANSITION
    _selection_no_links(root, successor_path)
    if successor_path.exists():
        return _blood_begets_skulls_test_successor(
            root,
            previous_runtime=record["runtime_fingerprint"],
            previous_transition=raw,
            previous_sources=record["sources"],
            previous_classification=record["updated_files"][classification_owner]["after"],
            brass_additions=_selection_members(record["added_files"], root),
        )
    for source, digest in record["sources"].items():
        _checked_bytes(root, source, digest)
    updated = _selection_members(
        {classification_owner: record["updated_files"][classification_owner]["after"]}, root
    )
    return (
        record["runtime_fingerprint"],
        updated,
        _selection_members(record["added_files"], root),
        raw,
    )


def _stage3_melee_profile_successor(
    root: Path, *, previous_runtime: str, previous_transition: bytes
) -> tuple[str, TestSuccessors, bytes] | None:
    name = "data/source_audits/ci64_provenance_v1/stage3-melee-profile-test-v1.json"
    path = root / name
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(
        root, name, "d6878ec80208f32f09e52fa324fe7237123dc90f403d2238139d020ba780df40"
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    owner = "tests/infrastructure/adapters/test_ordinary_melee_profile_policy.py"
    sources = {
        "src/warhammer40k_core/ai/ordinary_melee_profile_policy.py",
        "src/warhammer40k_core/ai/player_policy.py",
        "src/warhammer40k_core/ai/runner.py",
    }
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "added_files",
        }
        or record["schema"] != "finite-stage3-melee-profile-test-v1"
        or record["base"] != "5ebd32bf98f5313e7ef0790f601a88ee1a6eb8fe"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["sources"].keys() != sources
        or record["added_files"].keys() != {owner}
    ):
        raise SystemExit("Stage 3 melee profile test transition differs.")
    for source in sorted(sources):
        _checked_bytes(root, source, record["sources"][source])
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw


def _stage3_flight_normal_move_successor(
    root: Path, *, previous_runtime: str, previous_transition: bytes
) -> tuple[str, TestSuccessors, bytes] | None:
    name = "data/source_audits/ci64_provenance_v1/stage3-flight-normal-move-test-v1.json"
    path = root / name
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(
        root, name, "47ee27bbd227b22ae4f64bf6c148eb8944439e2a2245efc123451d0ea1e968bf"
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    owner = "tests/infrastructure/adapters/test_flight_normal_move_policy.py"
    source = "src/warhammer40k_core/ai/flight_normal_move_policy.py"
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "added_files",
        }
        or record["schema"] != "finite-stage3-flight-normal-move-test-v1"
        or record["base"] != "98f83a364d0a9ea8bef3fa00b02b4420948601fb"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["sources"].keys() != {source}
        or record["added_files"].keys() != {owner}
    ):
        raise SystemExit("Stage 3 flight Normal Move test transition differs.")
    _checked_bytes(root, source, record["sources"][source])
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw


CHARGE_FLIGHT_WALL_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/charge-flight-wall-test-v1.json"
)
CHARGE_FLIGHT_WALL_SHA256 = "93199961c9111e9cc0dd527f2b1224fd4a6e2c9e627ef735fac37cf7b30b5c27"
CHARGE_FLIGHT_WALL_BASE = "ccf3b3bed821d5fe92aa084f919100aaea3502e2"
CHARGE_FLIGHT_WALL_OWNER = "tests/infrastructure/adapters/test_charge_flight_barrier.py"
CHARGE_FLIGHT_ONSLAUGHT_OWNER = (
    "tests/infrastructure/adapters/test_charge_flight_onslaught_timing.py"
)


def _pre_roll_charge_flight_test_addition(
    root: Path, *, previous_runtime: str, previous_transition: bytes
) -> tuple[str, TestSuccessors, bytes] | None:
    name = "data/source_audits/ci64_provenance_v1/pre-roll-charge-flight-test-v1.json"
    path = root / name
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(
        root, name, "fd5511973dabe4068f618dec2f1f1419cb79f99629e831b9b14a810ab3cb110e"
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    owner = "tests/infrastructure/adapters/test_charge_flight_admission.py"
    source = "src/warhammer40k_core/ai/charge_flight_admission.py"
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "added_files",
        }
        or record["schema"] != "finite-pre-roll-charge-flight-test-v1"
        or record["base"] != "344129210b416dab7fc3dc79d1a4d467e7ebfa98"
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or record["sources"].keys() != {source}
        or record["added_files"].keys() != {owner}
    ):
        raise SystemExit("Pre-roll Charge flight test transition differs.")
    successor_path = root / CHARGE_FLIGHT_WALL_TRANSITION
    _selection_no_links(root, successor_path)
    if not successor_path.exists():
        _checked_bytes(root, source, record["sources"][source])
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw


def _charge_flight_wall_test_addition(
    root: Path,
    *,
    previous_runtime: str,
    previous_transition: bytes,
    original_charge_transition: bytes,
) -> tuple[str, TestSuccessors, bytes] | None:
    path = root / CHARGE_FLIGHT_WALL_TRANSITION
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(root, CHARGE_FLIGHT_WALL_TRANSITION, CHARGE_FLIGHT_WALL_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    source = "src/warhammer40k_core/ai/charge_flight_admission.py"
    predecessor = json.loads(original_charge_transition, object_pairs_hook=_selection_object)
    if (
        set(record)
        != {
            "schema",
            "base",
            "retained_transition_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "added_files",
        }
        or record["schema"] != "finite-charge-flight-wall-test-v1"
        or record["base"] != CHARGE_FLIGHT_WALL_BASE
        or record["retained_transition_sha256"] != hashlib.sha256(previous_transition).hexdigest()
        or record["retained_runtime_fingerprint"] != previous_runtime
        or set(record["sources"]) != {source}
        or set(record["added_files"]) != {CHARGE_FLIGHT_WALL_OWNER, CHARGE_FLIGHT_ONSLAUGHT_OWNER}
        or record["sources"][source]["before"] != predecessor["sources"][source]
    ):
        raise SystemExit("Charge flight wall test transition differs.")
    for name, binding in record["sources"].items():
        if set(binding) != {"before", "after"}:
            raise SystemExit("Charge flight wall test source binding differs.")
        _checked_bytes(root, name, binding["after"])
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw


COMBINED_CHARGE_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/combined-charge-admission-v1.json"
)
COMBINED_CHARGE_TRANSITION_SHA256 = (
    "85a8eb553ae08b36446c89ebccbc2081ea7e363984f77a462690f1eb348801ec"
)
COMBINED_CHARGE_BASE = "4d753ec652ee38b394260d3f539df7b04403149b"


COUNTEROFFENSIVE_FIGHT_TYPE_TRANSITION = (
    "data/source_audits/ci64_provenance_v1/counteroffensive-fight-type-v1.json"
)
COUNTEROFFENSIVE_FIGHT_TYPE_SHA256 = (
    "374958f528106e4b8d8b16f7a9c91d2dd26d03622cfd6a02596b0cf11f0f3a24"
)
COUNTEROFFENSIVE_FIGHT_TYPE_OWNER = "tests/rules/section12/test_counteroffensive_fight_type.py"
_COUNTEROFFENSIVE_FIGHT_TYPE_SOURCES = {
    "src/warhammer40k_core/engine/fight_activation_requests.py",
    "src/warhammer40k_core/engine/fight_order.py",
    "src/warhammer40k_core/engine/lifecycle_reaction_queue.py",
    "src/warhammer40k_core/engine/phases/fight.py",
    "src/warhammer40k_core/engine/stratagems_effect_handlers.py",
}


class _CounteroffensiveFightTypeReceipt(TypedDict):
    schema: str
    base: str
    retained_normal_move_sha256: str
    retained_runtime_fingerprint: str
    runtime_fingerprint: str
    runtime_manifest: dict[str, str]
    sources: SourceSuccessors
    origin_test: dict[str, dict[str, object]]
    added_files: TestSuccessors
    added_cases: list[str]


def _counteroffensive_fight_type_transition(
    root: Path,
) -> tuple[_CounteroffensiveFightTypeReceipt, bytes] | None:
    path = root / COUNTEROFFENSIVE_FIGHT_TYPE_TRANSITION
    _selection_no_links(root, path)
    if not path.exists():
        return None
    raw = _checked_bytes(
        root, COUNTEROFFENSIVE_FIGHT_TYPE_TRANSITION, COUNTEROFFENSIVE_FIGHT_TYPE_SHA256
    )
    receipt = cast(
        _CounteroffensiveFightTypeReceipt, json.loads(raw, object_pairs_hook=_selection_object)
    )
    if (
        receipt.keys() != _CounteroffensiveFightTypeReceipt.__required_keys__
        or receipt["schema"] != "finite-counteroffensive-fight-type-v1"
        or receipt["base"] != "dec50bca2394c755a0d5fb76e6659882b388c032"
        or receipt["runtime_fingerprint"] == receipt["retained_runtime_fingerprint"]
        or receipt["sources"].keys() != _COUNTEROFFENSIVE_FIGHT_TYPE_SOURCES
        or receipt["origin_test"].keys() != {"before", "after"}
        or receipt["added_files"].keys() != {COUNTEROFFENSIVE_FIGHT_TYPE_OWNER}
        or receipt["added_cases"]
        != [
            f"{COUNTEROFFENSIVE_FIGHT_TYPE_OWNER}::test_counteroffensive_preserves_native_fight_type[{case}]"
            for case in ("decline", "normal", "overrun", "single-overrun")
        ]
        or any(
            change.keys() != {"before", "after"} or change["before"] == change["after"]
            for change in (receipt["runtime_manifest"], *receipt["sources"].values())
        )
    ):
        raise SystemExit("Counteroffensive Fight-type test admission differs.")
    for name, change in receipt["sources"].items():
        _checked_bytes(root, name, change["after"])
    _checked_bytes(root, MANIFEST, receipt["runtime_manifest"]["after"])
    return receipt, raw


def combined_charge_runtime(root: Path, flight_raw: bytes, retry_raw: bytes) -> str:
    """Bind both independently validated lineages to their one composed runtime."""
    receipt = _checked_bytes(root, COMBINED_CHARGE_TRANSITION, COMBINED_CHARGE_TRANSITION_SHA256)
    binding = json.loads(receipt, object_pairs_hook=_selection_object)
    if (
        binding["schema"] != "combined-charge-admission-v1"
        or binding["base"] != COMBINED_CHARGE_BASE
        or hashlib.sha256(flight_raw).hexdigest() != binding["fools_flight_receipt_sha256"]
        or hashlib.sha256(retry_raw).hexdigest() != binding["ground_charge_receipt_sha256"]
    ):
        raise SystemExit("Combined Charge admission predecessor differs.")
    fingerprint = binding["combined_runtime_fingerprint"]
    if not isinstance(fingerprint, str):
        raise SystemExit("Combined Charge runtime fingerprint is malformed.")
    from scripts.stage2_ground_charge_test_admission import load_normal_move_admission

    normal_move = load_normal_move_admission(root)
    if normal_move is not None:
        counter = _counteroffensive_fight_type_transition(root)
        counter_receipt = None if counter is None else counter[0]
        normal_runtime = normal_move.admit_runtime(
            root,
            predecessor=receipt,
            fingerprint=fingerprint,
            manifest_sha256=binding["combined_manifest_sha256"],
            manifest_successor=None
            if counter_receipt is None
            else counter_receipt["runtime_manifest"],
        )
        if counter_receipt is None:
            return normal_runtime
        if (
            counter_receipt["retained_normal_move_sha256"]
            != hashlib.sha256(normal_move.raw).hexdigest()
            or counter_receipt["retained_runtime_fingerprint"] != normal_runtime
        ):
            raise SystemExit(
                "Counteroffensive Fight types require the exact Normal Move predecessor."
            )
        return counter_receipt["runtime_fingerprint"]
    _checked_bytes(root, MANIFEST, binding["combined_manifest_sha256"])
    return fingerprint


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
    pending_battle_shock = _pending_battle_shock_source_transition(root)
    pending_sources = {} if pending_battle_shock is None else pending_battle_shock[2]
    from scripts.dark_pact_test_admission import dark_pact_source_successors

    pact_sources = dark_pact_source_successors(root)
    attack_reroll_order_path = root / MONSTER_MASH_ATTACK_REROLL_TRANSITION
    _selection_no_links(root, attack_reroll_order_path)
    attack_reroll_order = (
        _monster_mash_attack_reroll_successor(
            root, retained_cutover_sha256, current_sources=pact_sources
        )
        if attack_reroll_order_path.exists()
        else None
    )
    round4_path = root / ROUND4_BATTLE_SHOCK_TRANSITION
    _selection_no_links(root, round4_path)
    round4 = None
    if round4_path.exists():
        if attack_reroll_order is None:
            raise SystemExit("Round 4 Battle-shock tests require the attack reroll predecessor.")
        round4 = _round4_battle_shock_successor(
            root,
            retained_cutover_sha256,
            attack_reroll_order[1],
            current_sources=pending_sources,
        )
    fight_reroll = (
        _stage2_fight_reroll_successor(
            root, current_sources={} if attack_reroll_order is None else attack_reroll_order[2]
        )
        if has_fight_reroll
        else None
    )
    source_successors: SourceSuccessors = {}
    test_successors: TestSuccessors = {}
    fight_successor = _stage2_fight_successor(root) if has_stage2_fight else None
    stage2_fight_tests = {} if fight_successor is None else fight_successor[1]
    gore = _gore_hungry_onslaught_transition(root)
    if has_gameplay_budget:
        if not has_codec:
            raise SystemExit("Gameplay movement budget tests require the oval codec predecessor.")
        budget_sources = {} if fight_reroll is None else dict(fight_reroll[3])
        if gore is not None:
            budget_source = _GORE_HUNGRY_ONSLAUGHT_BUDGET_SOURCE
            if budget_source in budget_sources:
                raise SystemExit("Gore-Hungry Onslaught duplicates a budget source successor.")
            budget_sources[budget_source] = gore[0]["historical_sources"][budget_source]
        runtime, source_successors, test_successors, successor_raw = _gameplay_budget_successor(
            root,
            current_tests=stage2_fight_tests,
            current_sources=budget_sources,
        )
        raw += b"\0" + successor_raw
    if fight_successor is not None:
        runtime, _, successor_raw = fight_successor
        raw += b"\0" + successor_raw
    counteroffensive_runtime = runtime
    counter_fight_type = _counteroffensive_fight_type_transition(root)
    counter_receipt = None if counter_fight_type is None else counter_fight_type[0]
    melee_restore_tests = None
    melee_restore_raw = None
    if has_melee_restore:
        runtime, melee_restore_tests, melee_restore_raw = _stage2_melee_restore_successor(
            root,
            current_tests=None if fight_reroll is None else fight_reroll[1],
            current_sources={} if counter_receipt is None else counter_receipt["sources"],
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
                _retained_source(root, name, digest, pending_sources)
            runtime = CAVALCADE_AUTHORITY_RUNTIME
    shadow_path = root / ROUND_FIVE_SHADOW_TRANSITION
    _selection_no_links(root, shadow_path)
    shadow = None
    if shadow_path.exists():
        if runtime != CAVALCADE_AUTHORITY_RUNTIME:
            raise SystemExit("Round-five Shadow tests require the Cavalcade authority predecessor.")
        shadow = _round_five_shadow_successor(
            root,
            retained_cutover_sha256=retained_cutover_sha256,
            current_sources={} if round4 is None else round4[1],
        )
        runtime = shadow[0]
    shalaxi_path = root / ROUND3_SHALAXI_TRANSITION
    _selection_no_links(root, shalaxi_path)
    shalaxi = _round3_shalaxi_successor(root) if shalaxi_path.exists() else None
    shooting_visibility_path = root / SHOOTING_VISIBILITY_TRANSITION
    _selection_no_links(root, shooting_visibility_path)
    shooting_visibility = (
        _shooting_visibility_successor(
            root,
            current_sources={} if shalaxi is None else shalaxi[2],
            current_tests=None if shalaxi is None else shalaxi[3],
        )
        if shooting_visibility_path.exists()
        else None
    )
    close_quarters_path = root / CLOSE_QUARTERS_TRANSITION
    _selection_no_links(root, close_quarters_path)
    close_quarters = None
    if close_quarters_path.exists():
        if shadow is None:
            raise SystemExit("Close Quarters tests require the Round-five Shadow predecessor.")
        close_quarters = _close_quarters_test_successor(
            root,
            retained_cutover_sha256=retained_cutover_sha256,
            predecessor_runtime=runtime,
            current_sources={
                **({} if shalaxi is None else shalaxi[2]),
                **({} if shooting_visibility is None else shooting_visibility[2]),
            },
            current_tests=(
                shalaxi[3]
                if shalaxi is not None
                else (None if shooting_visibility is None else shooting_visibility[3])
            ),
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
    opening_path = root / OPENING_SHADOW_FORM_TRANSITION
    _selection_no_links(root, opening_path)
    opening_raw = None
    opening_tests: TestSuccessors = {}
    if opening_path.exists():
        if cover_event_raw is None:
            raise SystemExit(
                "Opening Shadow Form tests require the Cover event identity predecessor."
            )
        runtime, opening_tests, opening_raw = _opening_shadow_form_test_successor(root, runtime)
    movement_path = root / OPENING_MOVEMENT_UNIT_ADDITION
    _selection_no_links(root, movement_path)
    movement_raw = None
    if movement_path.exists():
        if opening_raw is None:
            raise SystemExit("Opening Movement tests require the Shadow Form predecessor.")
        movement_raw = _checked_bytes(
            root, OPENING_MOVEMENT_UNIT_ADDITION, OPENING_MOVEMENT_UNIT_SHA256
        )
        movement = json.loads(movement_raw, object_pairs_hook=_selection_object)
        if (
            movement.keys()
            != {
                "schema",
                "retained_opening_shadow_form_sha256",
                "retained_runtime_fingerprint",
                "runtime_fingerprint",
                "policy_sha256",
                "added_files",
            }
            or movement["schema"] != "finite-stage2-opening-movement-unit-test-addition-v1"
            or movement["retained_opening_shadow_form_sha256"] != OPENING_SHADOW_FORM_SHA256
            or movement["retained_runtime_fingerprint"] != runtime
            or set(movement["added_files"]) != {OPENING_MOVEMENT_UNIT_OWNER}
        ):
            raise SystemExit("Opening Movement unit test addition differs.")
        _checked_bytes(root, OPENING_MOVEMENT_UNIT_POLICY, movement["policy_sha256"])
        additions.update(_selection_members(movement["added_files"], root))
        runtime = movement["runtime_fingerprint"]
    monster_mash_path = root / MONSTER_MASH_ADDITION
    _selection_no_links(root, monster_mash_path)
    monster_mash_raw = None
    if monster_mash_path.exists():
        if movement_raw is None:
            raise SystemExit("Monster Mash tests require the Opening Movement predecessor.")
        runtime, monster_mash_tests, monster_mash_raw = _monster_mash_addition(root, runtime)
        additions.update(monster_mash_tests)
    if shooting_visibility is not None:
        if monster_mash_raw is None or shooting_visibility[0] != runtime:
            raise SystemExit("Shooting visibility requires the exact Monster Mash predecessor.")
        runtime = shooting_visibility[1]
    if attack_reroll_order is not None:
        if shooting_visibility is None or attack_reroll_order[0] != runtime:
            raise SystemExit("Monster Mash attack reroll requires the exact Shooting predecessor.")
        runtime = attack_reroll_order[1]
    if round4 is not None:
        runtime = round4[0]
    malice_path = root / ROUND4_MALICE_BEARER_TRANSITION
    _selection_no_links(root, malice_path)
    malice = None
    if malice_path.exists():
        if round4 is None:
            raise SystemExit("Round 4 Malice bearer tests require the Battle-shock predecessor.")
        malice = _round4_malice_bearer_successor(root, retained_cutover_sha256, runtime)
        runtime = malice[0]
    if shalaxi is not None:
        if malice is None or shooting_visibility is None or shalaxi[0] != runtime:
            raise SystemExit("Round 3 Shalaxi tests require the exact Malice bearer predecessor.")
        runtime = shalaxi[1]
    from scripts.stage2_ground_charge_test_admission import (
        SCREEN_TRANSITION,
        SHOOTING_TRANSITION,
        ground_charge_retry_admission,
        ground_charge_test_successor,
        load_normal_move_admission,
        normal_move_origin_test_addition,
        normal_shooting_test_successor,
        rigid_ground_charge_test_successor,
        screen_movement_test_successor,
    )

    # The rigid successor supplies the current source digest for the older
    # group charge admission below. Authenticate its runtime predecessor first.
    regeneration = (
        None
        if pending_battle_shock is None
        else _grotesque_regeneration_test_successor(
            root,
            previous_runtime=pending_battle_shock[1],
            previous_transition=pending_battle_shock[3],
        )
    )
    rigid_charge = rigid_ground_charge_test_successor(
        root, previous_runtime=None if regeneration is None else regeneration[0]
    )
    retry_charge = ground_charge_retry_admission(root)
    normal_move = load_normal_move_admission(root)
    ground_charge = None
    ground_charge_path = root / GROUND_CHARGE_TEST_TRANSITION
    _selection_no_links(root, ground_charge_path)
    if ground_charge_path.exists():
        if shalaxi is None:
            raise SystemExit("Ground charge tests require the Shalaxi predecessor.")
        ground_charge = ground_charge_test_successor(
            root,
            transition_path=ground_charge_path,
            previous_runtime=runtime,
            previous_transition_sha256=ROUND3_SHALAXI_SHA256,
            rigid_source=None if rigid_charge is None else rigid_charge[1],
            retry=retry_charge,
        )
        runtime = ground_charge[0]

    shooting_path = root / SHOOTING_TRANSITION
    _selection_no_links(root, shooting_path)
    shooting = None
    if shooting_path.exists():
        if ground_charge is None:
            raise SystemExit("Normal Shooting tests require the ground charge predecessor.")
        shooting = normal_shooting_test_successor(
            root, previous_runtime=runtime, retained_cutover_sha256=retained_cutover_sha256
        )
        runtime = shooting[0]
    screen_path = root / SCREEN_TRANSITION
    _selection_no_links(root, screen_path)
    screen = None
    if screen_path.exists():
        if shooting is None:
            raise SystemExit("Screen movement tests require the Normal Shooting predecessor.")
        screen = screen_movement_test_successor(
            root, previous_runtime=runtime, normal_move=normal_move
        )
        runtime = screen[0]
    if pending_battle_shock is not None:
        if screen is None or pending_battle_shock[0] != runtime:
            raise SystemExit("Pending Battle-shock requires the exact Screen movement predecessor.")
        runtime = pending_battle_shock[1]
    if regeneration is not None:
        runtime = regeneration[0]
    brass = None
    stage3_flight = None
    charge_flight = None
    charge_flight_wall = None
    gore_additions: TestSuccessors = {}
    if rigid_charge is not None:
        if ground_charge is None:
            raise SystemExit("Rigid ground charge tests require the group charge predecessor.")
        runtime = rigid_charge[0]
        brass = _sheathed_in_brass_test_addition(
            root, previous_runtime=runtime, previous_transition=rigid_charge[3]
        )
        if brass is not None:
            runtime = brass[0]
            wrath_path = root / WRATH_UNDENIABLE_TRANSITION
            _selection_no_links(root, wrath_path)
            if wrath_path.exists():
                wrath_raw = _checked_bytes(
                    root, WRATH_UNDENIABLE_TRANSITION, WRATH_UNDENIABLE_TRANSITION_SHA256
                )
                if not brass[3].endswith(b"\0" + wrath_raw):
                    raise SystemExit("Wrath Undeniable is missing from the source lineage.")
                charge_flight = _pre_roll_charge_flight_test_addition(
                    root, previous_runtime=runtime, previous_transition=wrath_raw
                )
                if charge_flight is not None:
                    runtime = charge_flight[0]
            else:
                stage3_flight = _stage3_flight_normal_move_successor(
                    root, previous_runtime=runtime, previous_transition=brass[3]
                )
                if stage3_flight is not None:
                    runtime = stage3_flight[0]
    if gore is not None:
        record, _ = gore
        if (
            charge_flight is None
            or record["retained_runtime_fingerprint"] != runtime
            or record["retained_transition_sha256"] != hashlib.sha256(charge_flight[2]).hexdigest()
        ):
            raise SystemExit(
                "Gore-Hungry Onslaught requires the exact pre-roll Charge flight predecessor."
            )
        identity_source = _GORE_HUNGRY_ONSLAUGHT_IDENTITY_SOURCE
        if identity_source in source_successors:
            raise SystemExit("Gore-Hungry Onslaught duplicates an identity source successor.")
        source_successors[identity_source] = record["historical_sources"][identity_source]
        gore_additions = _selection_members(record["added_files"], root)
        runtime = record["runtime_fingerprint"]
    wall_path = root / CHARGE_FLIGHT_WALL_TRANSITION
    _selection_no_links(root, wall_path)
    if wall_path.exists():
        if gore is None or charge_flight is None:
            raise SystemExit("Charge flight wall tests require the Onslaught predecessor.")
        charge_flight_wall = _charge_flight_wall_test_addition(
            root,
            previous_runtime=runtime,
            previous_transition=gore[1],
            original_charge_transition=charge_flight[2],
        )
        if charge_flight_wall is not None:
            runtime = charge_flight_wall[0]
    from scripts.dark_pact_test_admission import dark_pact_test_transition

    pact = dark_pact_test_transition(
        root, runtime=runtime, active_successors={} if malice is None else malice[1]
    )
    if pact is not None:
        runtime, pact_updated, pact_added, pact_raw = pact
        test_successors.update(pact_updated)
    from scripts.fools_flight_test_admission import load_fools_flight_admission

    fools_flight = load_fools_flight_admission(root)
    flight_addition = None
    flight_runtime = None
    if fools_flight is not None:
        if pact is None:
            raise SystemExit("Fool's Flight requires the exact Dark Pact predecessor.")
        flight_runtime, flight_tests, flight_raw = fools_flight.admits_after(
            root=root, runtime=pact[0], predecessor=pact[3]
        )
        flight_addition = (flight_tests, flight_raw)
    retry_addition = None
    retry_runtime = None
    if retry_charge is not None:
        if pact is None or ground_charge is None:
            raise SystemExit(
                "Ground charge retry requires the Dark Pact and ground charge lineage."
            )
        # Bind to the historical Dark Pact receipt, not a parallel successor.
        retry_runtime, retry_tests, retry_raw = retry_charge.admit(
            root, runtime=pact[0], predecessor=pact[3]
        )
        retry_addition = (retry_tests, retry_raw)
    if flight_runtime is not None and retry_runtime is not None:
        if flight_addition is None or retry_addition is None:
            raise SystemExit("Combined Charge source admission is incomplete.")
        runtime = combined_charge_runtime(root, flight_addition[1], retry_addition[1])
    elif flight_runtime is not None:
        runtime = flight_runtime
    elif retry_runtime is not None:
        runtime = retry_runtime
    if counter_receipt is not None and normal_move is None:
        raise SystemExit("Counteroffensive Fight types require the Normal Move predecessor.")
    if normal_move is not None and (
        screen is None
        or runtime
        != (
            normal_move.receipt["runtime_fingerprint"]
            if counter_receipt is None
            else counter_receipt["runtime_fingerprint"]
        )
    ):
        raise SystemExit("Normal Move tests require the exact Screen and combined Charge lineage.")

    retained = _identity_test_transition(
        root,
        retained_cutover_sha256,
        runtime=runtime,
        source_successors=source_successors,
        test_successors={**test_successors, **opening_tests},
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
    if opening_raw is not None:
        if not opening_tests.keys() <= updated.keys():
            raise SystemExit("Opening Shadow Form must extend an existing active test owner.")
        updated.update(opening_tests)
        raw += b"\0" + opening_raw
    if movement_raw is not None:
        raw += b"\0" + movement_raw
    if monster_mash_raw is not None:
        raw += b"\0" + monster_mash_raw
    if shooting_visibility is not None:
        updated.update(shooting_visibility[3])
        raw += b"\0" + shooting_visibility[4]
    if attack_reroll_order is not None:
        updated.update(attack_reroll_order[3])
        raw += b"\0" + attack_reroll_order[4]
    if round4 is not None:
        _, _, round4_battle_shock, round4_raw = round4
        if round4_battle_shock.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Round 4 Battle-shock tests overlap the predecessor selection.")
        updated.update(round4_battle_shock)
        raw += b"\0" + round4_raw
    if malice is not None:
        _, malice_bearer, malice_raw = malice
        if malice_bearer.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Round 4 Malice bearer tests overlap the predecessor selection.")
        updated.update(malice_bearer)
        raw += b"\0" + malice_raw
    if shalaxi is not None:
        updated.update(shalaxi[3])
        raw += b"\0" + shalaxi[4]
    if ground_charge is not None:
        _, ground_charge_tests, ground_charge_raw = ground_charge
        if ground_charge_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Ground charge tests overlap the predecessor selection.")
        additions.update(ground_charge_tests)
        raw += b"\0" + ground_charge_raw
    if shooting is not None:
        _, shooting_tests, shooting_raw = shooting
        if shooting_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Normal Shooting tests overlap the predecessor selection.")
        updated.update(shooting_tests)
        raw += b"\0" + shooting_raw
    if screen is not None:
        _, screen_tests, screen_raw = screen
        if screen_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Screen movement tests overlap the predecessor selection.")
        additions.update(screen_tests)
        raw += b"\0" + screen_raw
    if pending_battle_shock is not None:
        raw += b"\0" + pending_battle_shock[3]
    if regeneration is not None:
        if regeneration[1].keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Grotesque Regeneration test update overlaps a prior transition.")
        updated.update(regeneration[1])
        raw += b"\0" + regeneration[2]
    if rigid_charge is not None:
        _, _, tests, rigid_raw = rigid_charge
        if tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Rigid ground charge tests overlap the predecessor selection.")
        additions.update(tests)
        raw += b"\0" + rigid_raw
    if brass is not None:
        _, brass_updates, brass_additions, brass_raw = brass
        if (brass_updates.keys() | brass_additions.keys()) & (
            updated.keys() | added.keys() | additions.keys()
        ):
            raise SystemExit("Sheathed in Brass tests overlap the predecessor selection.")
        updated.update(brass_updates)
        additions.update(brass_additions)
        raw += b"\0" + brass_raw
    if stage3_flight is not None:
        _, flight_tests, flight_raw = stage3_flight
        if flight_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Stage 3 flight Normal Move tests overlap the predecessor selection.")
        additions.update(flight_tests)
        raw += b"\0" + flight_raw
    if charge_flight is not None:
        _, charge_flight_tests, charge_flight_raw = charge_flight
        if charge_flight_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Pre-roll Charge flight tests overlap the predecessor selection.")
        additions.update(charge_flight_tests)
        raw += b"\0" + charge_flight_raw
    if gore is not None:
        if gore_additions.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Gore-Hungry Onslaught tests overlap predecessor tests.")
        additions.update(gore_additions)
        raw += b"\0" + gore[1]
    if charge_flight_wall is not None:
        _, wall_tests, wall_raw = charge_flight_wall
        if wall_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Charge flight wall tests overlap predecessor tests.")
        additions.update(wall_tests)
        raw += b"\0" + wall_raw
    if pact is not None:
        if pact_added.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Dark Pact tests overlap their predecessor selection.")
        updated.update(pact_updated)
        additions.update(pact_added)
        raw += b"\0" + pact_raw
    if flight_addition is not None:
        flight_tests, flight_raw = flight_addition
        if flight_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Fool's Flight tests overlap predecessor tests.")
        additions.update(flight_tests)
        raw += b"\0" + flight_raw
    if retry_addition is not None:
        retry_tests, retry_raw = retry_addition
        if retry_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Ground charge retry tests overlap their predecessor selection.")
        additions.update(retry_tests)
        raw += b"\0" + retry_raw
    if normal_move is not None:
        normal_tests = _selection_members(normal_move.receipt["added_files"], root)
        if normal_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Normal Move tests overlap predecessor tests.")
        additions.update(normal_tests)
        raw += b"\0" + normal_move.raw
    origin = normal_move_origin_test_addition(
        root,
        predecessor=normal_move,
        runtime=runtime
        if counter_receipt is None
        else counter_receipt["retained_runtime_fingerprint"],
        successor=None if counter_receipt is None else counter_receipt["origin_test"],
    )
    if origin is not None:
        origin_tests, origin_raw = origin
        if origin_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Constructed Normal Move origin tests overlap predecessor tests.")
        additions.update(origin_tests)
        raw += b"\0" + origin_raw
    if counter_fight_type is not None:
        counter_receipt, counter_raw = counter_fight_type
        counter_tests = _selection_members(counter_receipt["added_files"], root)
        if counter_tests.keys() & (updated.keys() | added.keys() | additions.keys()):
            raise SystemExit("Counteroffensive Fight-type tests overlap predecessor tests.")
        additions.update(counter_tests)
        raw += b"\0" + counter_raw
    return updated, {**added, **additions}, retained_raw + b"\0" + raw


def _round4_malice_bearer_successor(
    root: Path, retained_cutover_sha256: str, retained_runtime: str
) -> tuple[str, TestSuccessors, bytes]:
    from scripts.build_test_shards import CUTOVER_PATH

    raw = _checked_bytes(root, ROUND4_MALICE_BEARER_TRANSITION, ROUND4_MALICE_BEARER_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_round4_battle_shock_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-monster-mash-round4-malice-bearer-test-transition-v1"
        or record["base"] != ROUND4_MALICE_BEARER_BASE
        or record["retained_round4_battle_shock_sha256"] != ROUND4_BATTLE_SHOCK_SHA256
        or record["retained_runtime_fingerprint"] != retained_runtime
    ):
        raise SystemExit("Round 4 Malice bearer test transition differs.")
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    change = record["test"]
    if (
        set(change) != {"path", "before", "after"}
        or change["path"] != ROUND4_MALICE_BEARER_OWNER
        or change["before"] != cutover["active_files"][ROUND4_MALICE_BEARER_OWNER]
    ):
        raise SystemExit("Round 4 Malice bearer test predecessor differs.")
    _checked_bytes(root, ROUND4_MALICE_BEARER_SOURCE, record["source"]["after"])
    from scripts.dark_pact_test_admission import dark_pact_active_successors

    predecessors = {ROUND4_MALICE_BEARER_OWNER: change["after"]}
    successors = dark_pact_active_successors(root, predecessors)
    retained = _selection_members(predecessors, root, current=successors)
    return (
        record["runtime_fingerprint"],
        successors or retained,
        raw,
    )


def _round4_battle_shock_successor(
    root: Path,
    retained_cutover_sha256: str,
    retained_runtime: str,
    *,
    current_sources: SourceSuccessors,
) -> tuple[str, SourceSuccessors, TestSuccessors, bytes]:
    from scripts.build_test_shards import CUTOVER_PATH

    raw = _checked_bytes(root, ROUND4_BATTLE_SHOCK_TRANSITION, ROUND4_BATTLE_SHOCK_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_attack_reroll_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-monster-mash-round4-battle-shock-test-transition-v1"
        or record["base"] != ROUND4_BATTLE_SHOCK_BASE
        or record["retained_attack_reroll_sha256"] != MONSTER_MASH_ATTACK_REROLL_SHA256
        or record["retained_runtime_fingerprint"] != retained_runtime
        or set(record["source"]) != set(ROUND4_BATTLE_SHOCK_SOURCES)
    ):
        raise SystemExit("Round 4 Battle-shock test transition differs.")
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    change = record["test"]
    if (
        set(change) != {"path", "before", "after"}
        or change["path"] != ROUND4_BATTLE_SHOCK_OWNER
        or change["before"] != cutover["active_files"][ROUND4_BATTLE_SHOCK_OWNER]
    ):
        raise SystemExit("Round 4 Battle-shock test predecessor differs.")
    for name, source in record["source"].items():
        if set(source) != {"before", "after"}:
            raise SystemExit("Round 4 Battle-shock requires exact source digests.")
        _retained_source(root, name, source["after"], current_sources)
    return (
        record["runtime_fingerprint"],
        record["source"],
        _selection_members({ROUND4_BATTLE_SHOCK_OWNER: change["after"]}, root),
        raw,
    )


def _monster_mash_attack_reroll_successor(
    root: Path, retained_cutover_sha256: str, *, current_sources: SourceSuccessors | None = None
) -> tuple[str, str, SourceSuccessors, TestSuccessors, bytes]:
    from scripts.build_test_shards import CUTOVER_PATH

    raw = _checked_bytes(
        root, MONSTER_MASH_ATTACK_REROLL_TRANSITION, MONSTER_MASH_ATTACK_REROLL_SHA256
    )
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_shooting_visibility_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "source",
            "tests",
        }
        or record["schema"] != "finite-monster-mash-attack-reroll-test-transition-v1"
        or record["base"] != MONSTER_MASH_ATTACK_REROLL_BASE
        or record["retained_shooting_visibility_sha256"] != SHOOTING_VISIBILITY_SHA256
        or set(record["source"]) != set(MONSTER_MASH_ATTACK_REROLL_SOURCES)
        or set(record["tests"]) != set(MONSTER_MASH_ATTACK_REROLL_OWNERS)
    ):
        raise SystemExit("Monster Mash attack reroll test transition differs.")
    cutover = json.loads(
        _checked_bytes(root, CUTOVER_PATH, retained_cutover_sha256),
        object_pairs_hook=_selection_object,
    )
    tests = record["tests"]
    for owner, change in tests.items():
        if set(change) != {"before", "after"} or change["before"] != cutover["active_files"][owner]:
            raise SystemExit("Monster Mash attack reroll test predecessor differs.")
    for name, change in record["source"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit("Monster Mash attack reroll requires exact source digests.")
        _retained_source(root, name, change["after"], current_sources or {})
    return (
        record["retained_runtime_fingerprint"],
        record["runtime_fingerprint"],
        record["source"],
        _selection_members({name: change["after"] for name, change in tests.items()}, root),
        raw,
    )


def _round3_shalaxi_successor(
    root: Path,
) -> tuple[str, str, SourceSuccessors, TestSuccessors, bytes]:
    raw = _checked_bytes(root, ROUND3_SHALAXI_TRANSITION, ROUND3_SHALAXI_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_round4_malice_bearer_sha256",
            "retained_shooting_visibility_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "sources",
            "test",
        }
        or record["schema"] != "finite-monster-mash-round3-shalaxi-test-transition-v1"
        or record["base"] != ROUND3_SHALAXI_BASE
        or record["retained_round4_malice_bearer_sha256"] != ROUND4_MALICE_BEARER_SHA256
        or record["retained_shooting_visibility_sha256"] != SHOOTING_VISIBILITY_SHA256
        or set(record["sources"]) != set(ROUND3_SHALAXI_SOURCES)
        or set(record["test"]) != {"before", "after"}
    ):
        raise SystemExit("Round 3 Shalaxi test transition differs.")
    previous = json.loads(
        _checked_bytes(root, SHOOTING_VISIBILITY_TRANSITION, SHOOTING_VISIBILITY_SHA256),
        object_pairs_hook=_selection_object,
    )
    if record["test"]["before"] != previous["test"]["after"]:
        raise SystemExit("Round 3 Shalaxi test predecessor differs.")
    for name, change in record["sources"].items():
        if set(change) != {"before", "after"}:
            raise SystemExit("Round 3 Shalaxi sources require exact before and after digests.")
        _checked_bytes(root, name, change["after"])
    return (
        record["retained_runtime_fingerprint"],
        record["runtime_fingerprint"],
        record["sources"],
        _selection_members({CLOSE_QUARTERS_OWNER: record["test"]["after"]}, root),
        raw,
    )


def _shooting_visibility_successor(
    root: Path, *, current_sources: SourceSuccessors, current_tests: TestSuccessors | None
) -> tuple[str, str, SourceSuccessors, TestSuccessors, bytes]:
    raw = _checked_bytes(root, SHOOTING_VISIBILITY_TRANSITION, SHOOTING_VISIBILITY_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "base",
            "retained_close_quarters_sha256",
            "retained_monster_mash_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "source",
            "test",
        }
        or record["schema"] != "finite-monster-mash-shooting-visibility-test-transition-v1"
        or record["base"] != SHOOTING_VISIBILITY_BASE
        or record["retained_close_quarters_sha256"] != CLOSE_QUARTERS_SHA256
        or record["retained_monster_mash_sha256"] != MONSTER_MASH_SHA256
        or set(record["source"]) != {"before", "after"}
        or set(record["test"]) != {"before", "after"}
    ):
        raise SystemExit("Monster Mash Shooting visibility test transition differs.")
    previous = json.loads(
        _checked_bytes(root, CLOSE_QUARTERS_TRANSITION, CLOSE_QUARTERS_SHA256),
        object_pairs_hook=_selection_object,
    )
    if record["test"]["before"] != previous["test"][CLOSE_QUARTERS_OWNER]["after"]:
        raise SystemExit("Monster Mash Shooting visibility test predecessor differs.")
    _retained_source(root, SHOOTING_VISIBILITY_SOURCE, record["source"]["after"], current_sources)
    members = _selection_members(
        {CLOSE_QUARTERS_OWNER: record["test"]["after"]}, root, current=current_tests
    )
    return (
        record["retained_runtime_fingerprint"],
        record["runtime_fingerprint"],
        {SHOOTING_VISIBILITY_SOURCE: record["source"]},
        members,
        raw,
    )


def _monster_mash_addition(
    root: Path, predecessor_runtime: str
) -> tuple[str, TestSuccessors, bytes]:
    raw = _checked_bytes(root, MONSTER_MASH_ADDITION, MONSTER_MASH_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    if (
        record.keys()
        != {
            "schema",
            "retained_opening_movement_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "source_sha256",
            "added_files",
        }
        or record["schema"] != "finite-monster-mash-v995-test-addition-v1"
        or record["retained_opening_movement_sha256"] != OPENING_MOVEMENT_UNIT_SHA256
        or record["retained_runtime_fingerprint"] != predecessor_runtime
        or set(record["source_sha256"]) != set(MONSTER_MASH_SOURCES)
        or set(record["added_files"]) != {MONSTER_MASH_OWNER}
    ):
        raise SystemExit("Monster Mash v995 test addition differs.")
    for name, digest in record["source_sha256"].items():
        _checked_bytes(root, name, digest)
    return record["runtime_fingerprint"], _selection_members(record["added_files"], root), raw


def _opening_shadow_form_test_successor(
    root: Path, predecessor_runtime: str
) -> tuple[str, TestSuccessors, bytes]:
    from scripts.speedup_test_admission import ADDITION as SPEEDUP_ADDITION
    from scripts.speedup_test_admission import ADDITION_SHA256 as SPEEDUP_SHA256

    raw = _checked_bytes(root, OPENING_SHADOW_FORM_TRANSITION, OPENING_SHADOW_FORM_SHA256)
    record = json.loads(raw, object_pairs_hook=_selection_object)
    speedup_raw = _checked_bytes(root, SPEEDUP_ADDITION, SPEEDUP_SHA256)
    retained_owner = json.loads(speedup_raw, object_pairs_hook=_selection_object)["updated_files"][
        OPENING_SHADOW_FORM_OWNER
    ]
    if (
        record.keys()
        != {
            "schema",
            "retained_cover_event_identity_sha256",
            "retained_runtime_fingerprint",
            "runtime_fingerprint",
            "policy_sha256",
            "test",
        }
        or record["schema"] != "finite-stage2-opening-shadow-form-test-transition-v1"
        or record["retained_cover_event_identity_sha256"] != COVER_EVENT_IDENTITY_SHA256
        or record["retained_runtime_fingerprint"] != predecessor_runtime
        or record["test"].keys() != {"before", "after"}
        or record["test"]["before"] != retained_owner
    ):
        raise SystemExit("Opening Shadow Form test transition differs.")
    _checked_bytes(root, OPENING_SHADOW_FORM_POLICY, record["policy_sha256"])
    tests = _selection_members({OPENING_SHADOW_FORM_OWNER: record["test"]["after"]}, root)
    return record["runtime_fingerprint"], tests, raw


def _round_five_shadow_successor(
    root: Path, *, retained_cutover_sha256: str, current_sources: SourceSuccessors
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
        if name in current_sources:
            if current_sources[name]["before"] != change["after"]:
                raise SystemExit("Round-five Shadow source successor differs.")
            # The current transition checks these successor bytes.
        else:
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
    root: Path,
    *,
    retained_cutover_sha256: str,
    predecessor_runtime: str,
    current_sources: SourceSuccessors,
    current_tests: TestSuccessors | None,
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
        _retained_source(root, name, change["after"], current_sources)
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
    members = _selection_members({CLOSE_QUARTERS_OWNER: test["after"]}, root, current=current_tests)
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
    updated.update(
        _selection_members(speedup["updated_files"], root, current={**current_updated, **tests})
    )
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
