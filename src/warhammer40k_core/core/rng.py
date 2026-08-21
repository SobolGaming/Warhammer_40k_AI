from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from typing import Self, TypedDict, cast


class RandomSourceError(ValueError):
    """Raised when deterministic random input is invalid."""


class RandomSourcePayload(TypedDict):
    seed: str
    history: list[str]
    draw_count: int


@dataclass(slots=True)
class RandomSource:
    """Deterministic integer source mixed with explicit event/decision history."""

    seed: str
    history: tuple[str, ...]
    draw_count: int

    def __init__(
        self,
        seed: int | str,
        history: Iterable[str] = (),
        draw_count: int = 0,
    ) -> None:
        seed_text = str(seed)
        history_tuple = tuple(history)

        if not seed_text:
            raise RandomSourceError("RandomSource seed must not be empty.")
        if any(not token for token in history_tuple):
            raise RandomSourceError("RandomSource history tokens must not be empty.")
        if draw_count < 0:
            raise RandomSourceError("RandomSource draw_count must not be negative.")

        self.seed = seed_text
        self.history = history_tuple
        self.draw_count = draw_count

    def append_history(self, token: str) -> None:
        if not token:
            raise RandomSourceError("RandomSource history token must not be empty.")
        self.history = (*self.history, token)

    def fork(self, token: str) -> RandomSource:
        if not token:
            raise RandomSourceError("RandomSource fork token must not be empty.")
        return RandomSource(self.seed, (*self.history, token), self.draw_count)

    def history_digest(self) -> str:
        digest = sha256()
        digest.update(b"wh40k-core-v2-rng-history-v1")
        for token in self.history:
            digest.update(b"\x00")
            digest.update(token.encode("utf-8"))
        return digest.hexdigest()

    def randint_inclusive(self, low: int, high: int, *, stream_label: str) -> int:
        if low > high:
            raise RandomSourceError("RandomSource low bound must not exceed high bound.")
        if not stream_label.strip():
            raise RandomSourceError("RandomSource stream_label must not be empty.")

        span = high - low + 1
        limit = (1 << 256) - ((1 << 256) % span)
        nonce = 0

        while True:
            value = int.from_bytes(self._digest(stream_label, nonce), "big")
            if value < limit:
                self.draw_count += 1
                return low + (value % span)
            nonce += 1

    def to_payload(self) -> RandomSourcePayload:
        return {
            "seed": self.seed,
            "history": list(self.history),
            "draw_count": self.draw_count,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise RandomSourceError("RandomSource payload must be an object.")
        value = cast(dict[str, object], payload)
        if set(value) != {"seed", "history", "draw_count"}:
            raise RandomSourceError("RandomSource payload fields are invalid.")
        seed = value["seed"]
        history = value["history"]
        draw_count = value["draw_count"]
        if type(seed) is not str or not seed:
            raise RandomSourceError("RandomSource payload seed must be a non-empty string.")
        if type(history) is not list:
            raise RandomSourceError("RandomSource payload history must contain non-empty strings.")
        history_items = cast(list[object], history)
        if any(type(token) is not str or token == "" for token in history_items):
            raise RandomSourceError("RandomSource payload history must contain non-empty strings.")
        if type(draw_count) is not int or draw_count < 0:
            raise RandomSourceError(
                "RandomSource payload draw_count must be a non-negative integer."
            )
        return cls(
            seed=seed,
            history=cast(list[str], history_items),
            draw_count=draw_count,
        )

    def _digest(self, stream_label: str, nonce: int) -> bytes:
        digest = sha256()
        digest.update(b"wh40k-core-v2-rng-draw-v1")
        digest.update(b"\x00seed:")
        digest.update(self.seed.encode("utf-8"))
        digest.update(b"\x00history:")
        digest.update(self.history_digest().encode("ascii"))
        digest.update(b"\x00draw:")
        digest.update(str(self.draw_count).encode("ascii"))
        digest.update(b"\x00stream:")
        digest.update(stream_label.encode("utf-8"))
        digest.update(b"\x00nonce:")
        digest.update(str(nonce).encode("ascii"))
        return digest.digest()
