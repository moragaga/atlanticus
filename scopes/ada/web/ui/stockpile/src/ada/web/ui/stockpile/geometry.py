from __future__ import annotations

from collections.abc import Sequence

Point = tuple[float, float]
Profile = tuple[Point, ...]

_PROFILE_PHASES: dict[float, Profile] = {
    0.0: (
        (0.44, 0.00),
        (0.45, 0.00),
        (0.46, 0.00),
        (0.47, 0.00),
        (0.48, 0.00),
        (0.50, 0.00),
        (0.52, 0.00),
        (0.53, 0.00),
        (0.54, 0.00),
        (0.55, 0.00),
        (0.56, 0.00),
    ),
    0.30: (
        (0.20, 0.00),
        (0.24, 0.04),
        (0.31, 0.11),
        (0.39, 0.20),
        (0.46, 0.28),
        (0.51, 0.30),
        (0.57, 0.27),
        (0.65, 0.19),
        (0.73, 0.10),
        (0.79, 0.03),
        (0.82, 0.00),
    ),
    0.65: (
        (0.07, 0.00),
        (0.12, 0.08),
        (0.21, 0.23),
        (0.32, 0.40),
        (0.43, 0.57),
        (0.51, 0.65),
        (0.59, 0.62),
        (0.69, 0.49),
        (0.80, 0.30),
        (0.89, 0.10),
        (0.94, 0.00),
    ),
    1.0: (
        (0.00, 0.00),
        (0.06, 0.10),
        (0.16, 0.28),
        (0.28, 0.50),
        (0.40, 0.73),
        (0.49, 0.92),
        (0.57, 0.88),
        (0.68, 0.72),
        (0.80, 0.47),
        (0.92, 0.17),
        (1.00, 0.00),
    ),
}


def interpolate_profile(ratio: float) -> Profile:
    clipped = max(0.0, min(1.0, ratio))
    stops = tuple(sorted(_PROFILE_PHASES))
    for lower, upper in zip(stops, stops[1:], strict=True):
        if clipped <= upper:
            factor = (clipped - lower) / (upper - lower)
            return tuple(
                (
                    x0 + (x1 - x0) * factor,
                    y0 + (y1 - y0) * factor,
                )
                for (x0, y0), (x1, y1) in zip(
                    _PROFILE_PHASES[lower], _PROFILE_PHASES[upper], strict=True
                )
            )
    return _PROFILE_PHASES[stops[-1]]


def scaled_profile(profile: Sequence[Point]) -> Profile:
    return tuple((8.0 + x * 144.0, 115.0 - y * 92.0) for x, y in profile)


def closed_profile_path(points: Sequence[Point]) -> str:
    if len(points) < 2:
        raise ValueError('Stockpile profile requires at least two points')
    commands = [f'M {points[0][0]:.2f} {points[0][1]:.2f}']
    for index in range(len(points) - 1):
        previous = points[max(index - 1, 0)]
        current = points[index]
        following = points[index + 1]
        after = points[min(index + 2, len(points) - 1)]
        c1 = (
            current[0] + (following[0] - previous[0]) / 6.0,
            current[1] + (following[1] - previous[1]) / 6.0,
        )
        c2 = (
            following[0] - (after[0] - current[0]) / 6.0,
            following[1] - (after[1] - current[1]) / 6.0,
        )
        commands.append(
            f'C {c1[0]:.2f} {c1[1]:.2f} '
            f'{c2[0]:.2f} {c2[1]:.2f} '
            f'{following[0]:.2f} {following[1]:.2f}'
        )
    commands.append('Z')
    return ' '.join(commands)
