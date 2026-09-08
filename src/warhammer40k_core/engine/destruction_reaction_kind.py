from enum import StrEnum


class DestructionReactionKind(StrEnum):
    SHOOT_ON_DEATH = "shoot_on_death"
    FIGHT_ON_DEATH = "fight_on_death"
    SHOOT_OR_FIGHT_ON_DEATH = "shoot_or_fight_on_death"
    DEADLY_DEMISE = "deadly_demise"
