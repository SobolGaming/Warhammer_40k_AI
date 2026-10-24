"""Native partial-faction Command consumers at explicit component checkpoints."""

from tests.phase11c_command_phase_helpers import (
    destroy_models_with_recorded_mortal_wounds,
)
from tests.support.faction_batch01 import (
    CRUSHERS,
    RANGERS,
    Scene,
    anchor,
    locate,
    request,
    scene,
    selection,
)
from tests.support.section02_fixtures import Section02Definitions

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.destruction_provenance import DestructionSourceKind
from warhammer40k_core.engine.direct_mortal_wound_application import (
    apply_direct_mortal_wounds_to_unit,
)
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose


def command_scene(
    definitions: Section02Definitions,
    *,
    manifestation: bool = False,
    inside: bool = True,
    seed: int = 0,
    wounded: bool = True,
) -> Scene:
    s = scene(
        definitions,
        (selection(definitions, CRUSHERS, "daemon"),),
        (selection(definitions, RANGERS, "target"),),
        phase=BattlePhase.COMMAND,
        active="owner" if manifestation else "opponent",
        seed=f"b04-{seed}",
    )
    target_id = "own:daemon" if manifestation else "foe:target"
    target = s.units[target_id]
    x = 10.0 if inside else 38.0
    locate(
        s,
        target_id,
        tuple(Pose.at(x, 15 + i * 2.5) for i in range(len(target.own_models))),
    )
    # Place the complete muster, then use recorded engine destruction for the
    # prior-casualty premise. The artificial casualty source is not native credit.
    anchor(s)
    destroy_models_with_recorded_mortal_wounds(
        state=s.state,
        decisions=s.session.lifecycle.decision_controller,
        unit_instance_id=target_id,
        model_instance_ids=target.own_model_ids()[1 if manifestation else 2 :],
        application_id="fixture:b04-casualties",
        destroying_player_id="opponent" if manifestation else "owner",
    )
    if manifestation and wounded:
        apply_direct_mortal_wounds_to_unit(
            state=s.state,
            decisions=s.session.lifecycle.decision_controller,
            application_id="fixture:b04-wounded",
            source_rule_id="fixture:b04-wounded:source",
            source_context={"source_kind": "fixture_preexisting_casualties"},
            destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
                state=s.state,
                destroying_player_id="opponent",
                source_rules_unit_instance_id=None,
                source_model_instance_id=None,
                destruction_source_kind=DestructionSourceKind.ABILITY,
                action_phase=BattlePhase.COMMAND,
                source_step="fixture_preexisting_casualties",
            ),
            target_unit_instance_id=target_id,
            mortal_wounds=3,
        )
    return s


def decline_bravery(s: Scene) -> LifecycleStatus:
    r = request(
        s.session.advance_until_decision_or_terminal(),
        "submit_stratagem_target_proposal",
    )
    assert s.state.command_point_total("owner") == 1
    assert s.state.command_point_total("opponent") == 1
    return s.session.submit_parameterized_payload(
        request_id=r.request_id,
        payload=stratagem_decline_payload(),
        result_id="b04:bravery-declined",
    )


def health(session: LocalGameSession, unit_id: str) -> int:
    assert session.lifecycle.state is not None
    return sum(
        m.current_wounds
        for a in session.lifecycle.state.army_definitions
        for u in a.units
        if u.unit_instance_id == unit_id
        for m in u.own_models
    )
