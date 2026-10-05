"""Choose the physical leading-first order for a fixture's uniform translation."""

from warhammer40k_core.geometry.pathing import ModelPath


def leading_first_translation_paths(
    paths: tuple[ModelPath, ...],
    *,
    dx: float,
    dy: float = 0.0,
) -> tuple[ModelPath, ...]:
    return tuple(
        sorted(
            paths,
            key=lambda row: (
                -(row[1][0].position.x * dx + row[1][0].position.y * dy),
                row[0],
            ),
        )
    )
