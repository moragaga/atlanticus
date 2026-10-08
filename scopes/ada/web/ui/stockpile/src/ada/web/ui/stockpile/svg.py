from __future__ import annotations

import base64

from .geometry import closed_profile_path, interpolate_profile, scaled_profile


def build_stockpile_svg(height_m: float, *, scale_max_m: float) -> str:
    ratio = min(height_m / scale_max_m, 1.0)
    path = closed_profile_path(scaled_profile(interpolate_profile(ratio)))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 130" '
        'width="160" height="130" role="presentation">'
        '<defs>'
        '<linearGradient id="ore" x1="0" y1="0" x2="1" y2="0.6">'
        '<stop offset="0%" stop-color="#555e69"/>'
        '<stop offset="50%" stop-color="#9098a0"/>'
        '<stop offset="100%" stop-color="#48505a"/>'
        '</linearGradient>'
        '<linearGradient id="shine" x1="0" y1="0" x2="0.9" y2="1">'
        '<stop offset="0%" stop-color="#ffffff" stop-opacity=".26"/>'
        '<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>'
        '</linearGradient>'
        '</defs>'
        '<ellipse cx="80" cy="118" rx="65" ry="5" fill="#353b44" opacity=".15"/>'
        f'<path d="{path}" fill="url(#ore)"/>'
        f'<path d="{path}" fill="url(#shine)"/>'
        '<path d="M 10 117 L 150 117" stroke="#69727c" '
        'stroke-width="1.5" stroke-linecap="round" opacity=".45"/>'
        '</svg>'
    )


def build_stockpile_data_uri(height_m: float, *, scale_max_m: float) -> str:
    markup = build_stockpile_svg(height_m, scale_max_m=scale_max_m)
    return 'data:image/svg+xml;base64,' + base64.b64encode(markup.encode('utf-8')).decode('ascii')
