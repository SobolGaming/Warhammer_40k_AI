"""Fight entitlement tokens, distinct from historical engagement facts."""

from enum import StrEnum


class FightEligibilityKind(StrEnum):
    CHARGED_THIS_TURN = "charged_this_turn"
    CURRENTLY_ENGAGED = "currently_engaged"
    ENGAGED_AT_FIGHT_STEP_START = "engaged_at_fight_step_start"
    FORCED_ACTIVATION = "forced_activation"
