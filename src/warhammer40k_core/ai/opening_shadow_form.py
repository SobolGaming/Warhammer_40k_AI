"""An opt-in round-one Shadow Form policy based on public initiative."""

from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRegistration,
    PolicyRoute,
)
from warhammer40k_core.engine.battle_round_hooks import (
    SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_shadow_form_runtime import CATALOG_SHADOW_FORM_SUBMISSION_KIND

OPENING_SHADOW_FORM_POLICY_ID = "opening-shadow-form-initiative-v1"

_SOURCE = "gw-11e-chaos-daemons-datasheet-ir-2026-27:datasheet:000001148"
_SHADOW_FORM = f"{_SOURCE}:6"
_WREATHED_IN_SHADOWS = f"{_SOURCE}:8"
_PALL_OF_DESPAIR = f"{_SOURCE}:9"
_SHADOW_LORD = f"{_SOURCE}:10"
_FORMS = frozenset((_WREATHED_IN_SHADOWS, _PALL_OF_DESPAIR, _SHADOW_LORD))


def _route(actor_id: str) -> PolicyRoute:
    return PolicyRoute(
        actor_id,
        SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE,
        "battle",
        None,
        "command",
        None,
    )


class OpeningShadowFormPolicy:
    """Favor attack rerolls when acting first and ranged protection when acting second."""

    def choose(self, context: PlayerDecisionContext) -> PolicyAction:
        actor_id = context.route.actor_id
        view = context.observation
        payload = context.request["payload"]
        active = view["active_player_id"]
        if (
            context.route != _route(actor_id)
            or view["battle_round"] != 1
            or active is None
            or active not in view["player_ids"]
            or not isinstance(payload, dict)
            or payload.get("submission_kind") != CATALOG_SHADOW_FORM_SUBMISSION_KIND
            or payload.get("hook_id") != CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID
            or payload.get("source_rule_id") != _SHADOW_FORM
            or payload.get("battle_round") != 1
            or payload.get("player_id") != actor_id
            or payload.get("active_player_id") != active
        ):
            raise PolicyError("Opening Shadow Form requires Be'lakor's round-one request.")

        candidates = FiniteCandidateSet.from_context(context)
        by_source: dict[str, str] = {}
        for candidate in candidates.candidates:
            option = candidate.option
            detail = option["payload"]
            source = (
                detail.get("selected_shadow_form_source_id") if isinstance(detail, dict) else None
            )
            if not isinstance(source, str) or source in by_source:
                raise PolicyError("Opening Shadow Form requires unique issued form sources.")
            by_source[source] = option["option_id"]
        if by_source.keys() != _FORMS:
            raise PolicyError("Opening Shadow Form requires the three supported form sources.")

        preferred = _SHADOW_LORD if actor_id == active else _WREATHED_IN_SHADOWS
        return candidates.select(context, by_source[preferred])


def opening_shadow_form_registration(actor_id: str) -> PolicyRegistration:
    """Register explicitly per actor in a workload that uses the opening heuristic."""
    return PolicyRegistration(
        _route(actor_id),
        OPENING_SHADOW_FORM_POLICY_ID,
        '{"battle_round":1}',
        OpeningShadowFormPolicy(),
    )
