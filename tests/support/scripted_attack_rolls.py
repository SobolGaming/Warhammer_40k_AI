"""Predeclared dice at a native executor boundary without replacing its roll engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.engine.decision import DiceRollManager

if TYPE_CHECKING:
    from warhammer40k_core.core.dice import DiceRollSpec
    from warhammer40k_core.engine.event_log import EventLog

_Result = TypeVar("_Result")


class ScriptedAttackRolls:
    """Pass only the unconsumed plan to the executor on each legitimate resume."""

    def __init__(self, entries: tuple[tuple[DiceRollSpec, int], ...]) -> None:
        assert entries
        assert len({spec for spec, _ in entries}) == len(entries)
        self._entries = entries
        self._offset = 0
        self._journal: EventLog | None = None

    def run(
        self,
        resolve: Callable[..., _Result],
        arguments: dict[str, Any],
        *,
        manager_parameter: Literal["dice_manager", "manager"],
    ) -> _Result:
        journal: EventLog = arguments["decisions"].event_log
        if self._journal is None:
            self._journal = journal
        assert self._journal is journal
        initial = len(journal.records)
        previous_rolls = sum(event.event_type == "dice_rolled" for event in journal.records)
        expected = tuple(
            DiceRollResult.from_values(
                roll_id=f"roll-{previous_rolls + index:06d}",
                spec=spec,
                values=(face,),
                source="fixed",
            )
            for index, (spec, face) in enumerate(self._entries[self._offset :], 1)
        )
        manager = DiceRollManager(
            arguments["state"].private_rng_seed,
            event_log=journal,
            injected_results=expected,
        )
        result = resolve(**{**arguments, manager_parameter: manager})
        actual = [
            event.payload
            for event in journal.records_since(initial)
            if event.event_type == "dice_rolled"
        ]
        assert actual == [roll.to_payload() for roll in expected[: len(actual)]]
        remaining = tuple(manager._injected_results)  # pyright: ignore[reportPrivateUsage]
        assert remaining == expected[len(actual) :], "Unexpected pending dice prescription"
        self._offset += len(actual)
        return result

    def assert_consumed(self) -> None:
        assert self._offset == len(self._entries), (self._offset, self._entries)
