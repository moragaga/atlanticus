from __future__ import annotations

from dataclasses import dataclass
from html import escape

from flask import Response


@dataclass(frozen=True, slots=True)
class StatusPageAction:
    label: str
    href: str

    def __post_init__(self) -> None:
        label = self.label.strip()
        href = self.href.strip()
        if not label:
            raise ValueError('Status page action label must not be empty')
        if not href and self.href != '':
            raise ValueError('Status page action href must not be empty')
        object.__setattr__(self, 'label', label)
        object.__setattr__(self, 'href', href)


def status_page_response(
    *,
    status_code: int,
    title: str,
    message: str,
    action: StatusPageAction | None = None,
) -> Response:
    normalized_title = title.strip()
    normalized_message = message.strip()
    if not normalized_title:
        raise ValueError('Status page title must not be empty')
    if not normalized_message:
        raise ValueError('Status page message must not be empty')
    action_markup = ''
    if action is not None:
        action_markup = (
            f'<a class="atlanticus-status__action" href="{escape(action.href, quote=True)}">'
            f'{escape(action.label)}</a>'
        )
    body = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(normalized_title)} · Atlanticus</title>
<style>
:root{{
--atlanticus-navy:#0D1B2A;
--atlanticus-navy-dark:#071522;
--atlanticus-gold:#C9A24B;
--atlanticus-warm:#F5F1E6;
--atlanticus-white:#FFFFFF;
}}
html,body{{
height:100%;
margin:0;
font-family:Inter,Helvetica,Arial,sans-serif;
background:var(--atlanticus-warm);
color:var(--atlanticus-navy);
}}
body{{display:grid;place-items:center}}
main{{
width:min(36rem,calc(100% - 3rem));
box-sizing:border-box;
padding:2.25rem;
background:var(--atlanticus-white);
border:1px solid rgba(13,27,42,.12);
border-top:.25rem solid var(--atlanticus-gold);
border-radius:1rem;
box-shadow:0 1rem 2.5rem rgba(7,21,34,.12);
text-align:center;
}}
h1{{margin:0 0 .75rem;font-size:1.75rem;line-height:1.15}}
p{{margin:0;color:#52606D;font-size:1rem;line-height:1.55}}
.atlanticus-status__action{{
display:inline-flex;
margin-top:1.5rem;
padding:.72rem 1.05rem;
border-radius:.65rem;
background:var(--atlanticus-navy-dark);
color:var(--atlanticus-white);
font-weight:700;
text-decoration:none;
}}
.atlanticus-status__action:focus-visible{{
outline:.2rem solid var(--atlanticus-gold);
outline-offset:.2rem;
}}
</style>
</head>
<body>
<main>
<h1>{escape(normalized_title)}</h1>
<p>{escape(normalized_message)}</p>
{action_markup}
</main>
</body>
</html>"""
    response = Response(body, status=status_code, content_type='text/html; charset=utf-8')
    response.headers['Cache-Control'] = 'no-store'
    return response
