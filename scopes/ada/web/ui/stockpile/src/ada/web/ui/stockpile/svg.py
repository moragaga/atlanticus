from __future__ import annotations

import base64
from dataclasses import dataclass

from .geometry import (
    build_irregular_fill_path,
    interpolate_profile,
    render_pile_geometry,
)
from .models import StockpileDefinition, StockpileVariant


@dataclass(frozen=True, slots=True)
class StockpileRenderValues:
    percent: float
    height_ratio: float
    percent_text: str
    height_text: str | None


def build_stockpile_svg(definition: StockpileDefinition, values: StockpileRenderValues) -> str:
    variable_height = definition.variant is StockpileVariant.VARIABLE_HEIGHT
    width = 210 if variable_height else 102
    height = 172 if variable_height else 136
    content = _build_stockpile_content(definition, values, width=width, height=height)
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
        width="{width}" height="{height}"
        viewBox="0 0 {width} {height}"
        role="img" aria-label="Stockpile">
        {_build_definitions()}
        {content}
    </svg>"""


def build_stockpile_data_uri(definition: StockpileDefinition, values: StockpileRenderValues) -> str:
    svg = build_stockpile_svg(definition, values)
    payload = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f'data:image/svg+xml;base64,{payload}'


def _build_definitions() -> str:
    return """
    <defs>
        <pattern id="stockpile-light-texture"
            width="13" height="11"
            patternUnits="userSpaceOnUse">
            <circle cx="2" cy="3" r="0.8" fill="#8f8f8f" opacity="0.46"/>
            <circle cx="9" cy="7" r="1.0" fill="#9b9b9b" opacity="0.38"/>
            <path d="M 4 9 L 7 6 L 11 9"
                fill="none" stroke="#929292" stroke-width="0.65" opacity="0.38"/>
            <path d="M 0 6 L 3 5"
                stroke="#a2a2a2" stroke-width="0.7" opacity="0.45"/>
        </pattern>
        <pattern id="stockpile-dark-texture"
            width="12" height="10"
            patternUnits="userSpaceOnUse">
            <circle cx="3" cy="2" r="0.9" fill="#4f4f4f" opacity="0.42"/>
            <circle cx="9" cy="7" r="0.8" fill="#515151" opacity="0.38"/>
            <path d="M 1 8 L 5 5 L 8 8"
                fill="none" stroke="#4d4d4d" stroke-width="0.75" opacity="0.48"/>
            <path d="M 7 1 L 11 3"
                stroke="#565656" stroke-width="0.7" opacity="0.42"/>
        </pattern>
        <linearGradient id="stockpile-light-volume" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#a7a7a7"/>
            <stop offset="39%" stop-color="#d0d0d0"/>
            <stop offset="57%" stop-color="#ececec"/>
            <stop offset="76%" stop-color="#bcbcbc"/>
            <stop offset="100%" stop-color="#989898"/>
        </linearGradient>
        <linearGradient id="stockpile-dark-volume" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#666666"/>
            <stop offset="42%" stop-color="#858585"/>
            <stop offset="64%" stop-color="#707070"/>
            <stop offset="100%" stop-color="#5a5a5a"/>
        </linearGradient>
    </defs>
    """


def _build_stockpile_content(
    definition: StockpileDefinition,
    values: StockpileRenderValues,
    *,
    width: int,
    height: int,
) -> str:
    variable_height = definition.variant is StockpileVariant.VARIABLE_HEIGHT
    pile_width = width - (20 if variable_height else 14)
    pile_height = 110 if variable_height else 84
    pile_x = (width - pile_width) / 2
    base_y = height - (40 if variable_height else 35)
    pile_y = base_y - pile_height

    height_ratio = values.height_ratio if variable_height else 1.0
    geometry = render_pile_geometry(
        points=interpolate_profile(height_ratio),
        x=pile_x,
        y=pile_y,
        width=pile_width,
        height=pile_height,
    )

    visible_height = geometry.base_y - geometry.apex_y
    fill_y = geometry.base_y - visible_height * values.percent / 100
    fill_path = (
        build_irregular_fill_path(
            key=f'{definition.key}:{values.percent:.3f}',
            x=pile_x,
            width=pile_width,
            fill_y=fill_y,
            base_y=geometry.base_y,
        )
        if values.percent > 0
        else None
    )
    clip_id = 'stockpile-clip'
    badge_width = (
        104 if values.percent_text == 'Sin información' else (52 if variable_height else 46)
    )
    badge_height = 20 if variable_height else 19
    badge_x = (width - badge_width) / 2
    badge_y = base_y + (12 if variable_height else 9)
    badge_background = definition.percentage_background_color or '#4f4f4f'
    badge_text = definition.percentage_text_color or '#f4f4f4'

    measurement = ''
    if variable_height and values.height_text is not None:
        measurement_y = max(16, geometry.apex_y - 10)
        measurement = f"""
        <line x1="{geometry.apex_x:.2f}" y1="{measurement_y + 4:.2f}"
            x2="{geometry.apex_x:.2f}" y2="{geometry.apex_y - 2:.2f}"
            stroke="#6c6c6c" stroke-width="0.75" stroke-dasharray="2 2"/>
        <text x="{geometry.apex_x:.2f}" y="{measurement_y:.2f}"
            text-anchor="middle"
            font-family="Arial, Helvetica, sans-serif"
            font-size="11"
            font-weight="700"
            fill="#444444">{values.height_text}</text>
        """

    fill_markup = (
        ''
        if fill_path is None
        else f"""
        <path d="{fill_path}"
            clip-path="url(#{clip_id})"
            fill="url(#stockpile-dark-volume)"/>
        <path d="{fill_path}"
            clip-path="url(#{clip_id})"
            fill="url(#stockpile-dark-texture)"
            opacity="0.78"/>
    """
    )

    base_markup = (
        ''
        if fill_path is None
        else f"""
        <path d="{geometry.path}"
            fill="url(#stockpile-light-volume)"
            stroke="#666666"
            stroke-width="1.1"
            stroke-linejoin="round"/>
        <path d="{geometry.path}"
            fill="url(#stockpile-light-texture)"
            opacity="0.72"/>
    """
    )

    return f"""
    <g>
        <clipPath id="{clip_id}">
            <path d="{geometry.path}"/>
        </clipPath>
        {base_markup}
        {fill_markup}
        <path d="{geometry.path}"
            fill="none"
            stroke="#5e5e5e"
            stroke-width="1.1"
            stroke-linejoin="round"/>
        <rect x="{geometry.base_left_x - 7:.2f}" y="{geometry.base_y - 1:.2f}"
            width="{geometry.base_right_x - geometry.base_left_x + 14:.2f}"
            height="5" rx="1.5"
            fill="#868686" stroke="#5f5f5f" stroke-width="0.8"/>
        {measurement}
        <rect x="{badge_x:.2f}" y="{badge_y:.2f}"
            width="{badge_width}" height="{badge_height}" rx="3"
            fill="{badge_background}" fill-opacity="0.94"/>
        <text x="{badge_x + badge_width / 2:.2f}"
            y="{badge_y + badge_height * 0.73:.2f}"
            text-anchor="middle"
            font-family="Arial, Helvetica, sans-serif"
            font-size="{13 if variable_height else 12}"
            font-weight="700"
            fill="{badge_text}">{values.percent_text}</text>
    </g>
    """
