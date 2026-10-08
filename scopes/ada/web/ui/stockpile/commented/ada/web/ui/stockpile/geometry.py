# Geometría individual reutilizable: interpolación y trayectorias de relleno.
# Equivalente al archivo productivo, con explicación pedagógica en español.
from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass


Point = tuple[float, float]


@dataclass(frozen=True, slots=True)
class RenderedPileGeometry:
    path: str
    apex_x: float
    apex_y: float
    base_left_x: float
    base_right_x: float
    base_y: float


_REFERENCE_PROFILES: dict[float, tuple[Point, ...]] = {
    0.0: (
        (0.46, 1.00),
        (0.47, 0.99),
        (0.48, 0.985),
        (0.49, 0.98),
        (0.50, 0.975),
        (0.51, 0.98),
        (0.52, 0.985),
        (0.53, 0.99),
        (0.54, 1.00),
    ),
    8 / 30: (
        (0.31, 1.00),
        (0.34, 0.93),
        (0.38, 0.84),
        (0.43, 0.76),
        (0.50, 0.71),
        (0.56, 0.75),
        (0.62, 0.84),
        (0.67, 0.93),
        (0.70, 1.00),
    ),
    16 / 30: (
        (0.18, 1.00),
        (0.23, 0.87),
        (0.30, 0.70),
        (0.39, 0.54),
        (0.50, 0.43),
        (0.60, 0.52),
        (0.70, 0.69),
        (0.78, 0.87),
        (0.83, 1.00),
    ),
    23 / 30: (
        (0.08, 1.00),
        (0.14, 0.83),
        (0.23, 0.59),
        (0.36, 0.35),
        (0.49, 0.20),
        (0.61, 0.31),
        (0.75, 0.57),
        (0.86, 0.82),
        (0.92, 1.00),
    ),
    1.0: (
        (0.03, 1.00),
        (0.10, 0.78),
        (0.20, 0.50),
        (0.34, 0.24),
        (0.49, 0.07),
        (0.62, 0.20),
        (0.78, 0.48),
        (0.90, 0.77),
        (0.97, 1.00),
    ),
}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def interpolate_profile(height_ratio: float) -> tuple[Point, ...]:
    ratio = clamp(height_ratio, 0.0, 1.0)
    stops = sorted(_REFERENCE_PROFILES)

    if ratio <= stops[0]:
        return _REFERENCE_PROFILES[stops[0]]
    if ratio >= stops[-1]:
        return _REFERENCE_PROFILES[stops[-1]]

    left_stop = stops[0]
    right_stop = stops[-1]

    for current_left, current_right in zip(stops, stops[1:], strict=False):
        if current_left <= ratio <= current_right:
            left_stop = current_left
            right_stop = current_right
            break

    factor = (ratio - left_stop) / (right_stop - left_stop)
    left_points = _REFERENCE_PROFILES[left_stop]
    right_points = _REFERENCE_PROFILES[right_stop]

    return tuple(
        (
            left_x + (right_x - left_x) * factor,
            left_y + (right_y - left_y) * factor,
        )
        for (left_x, left_y), (right_x, right_y) in zip(left_points, right_points, strict=True)
    )


def render_pile_geometry(
    *,
    points: Sequence[Point],
    x: float,
    y: float,
    width: float,
    height: float,
) -> RenderedPileGeometry:
    scaled = tuple((x + px * width, y + py * height) for px, py in points)
    path_parts = [f"M {scaled[0][0]:.2f} {scaled[0][1]:.2f}"]
    path_parts.extend(f"L {px:.2f} {py:.2f}" for px, py in scaled[1:])
    path_parts.append(f"L {scaled[0][0]:.2f} {scaled[0][1]:.2f}")
    path_parts.append("Z")

    apex_x, apex_y = min(scaled, key=lambda point: point[1])
    base_y = max(point[1] for point in scaled)

    return RenderedPileGeometry(
        path=" ".join(path_parts),
        apex_x=apex_x,
        apex_y=apex_y,
        base_left_x=scaled[0][0],
        base_right_x=scaled[-1][0],
        base_y=base_y,
    )


def build_irregular_fill_path(
    *,
    key: str,
    x: float,
    width: float,
    fill_y: float,
    base_y: float,
) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    points: list[Point] = []

    for index in range(11):
        px = x + width * index / 10
        noise = (digest[index] / 255 - 0.5) * 5.0
        points.append((px, fill_y + noise))

    path_parts = [f"M {points[0][0]:.2f} {base_y:.2f}"]
    path_parts.append(f"L {points[0][0]:.2f} {points[0][1]:.2f}")
    path_parts.extend(f"L {px:.2f} {py:.2f}" for px, py in points[1:])
    path_parts.append(f"L {points[-1][0]:.2f} {base_y:.2f}")
    path_parts.append("Z")
    return " ".join(path_parts)
