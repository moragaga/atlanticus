from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from atlanticus.web.errors import WebDefinitionError

_LANGUAGE_PATTERN = re.compile(r'^[A-Za-z0-9-]+$')


@dataclass(frozen=True, slots=True)
class IndexContribution:
    head_fragments: tuple[str, ...] = ()
    body_start_fragments: tuple[str, ...] = ()
    body_end_fragments: tuple[str, ...] = ()
    runtime_config: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class IndexPageDefinition:
    language: str = 'es'
    head_fragments: tuple[str, ...] = ()
    body_start_fragments: tuple[str, ...] = ()
    body_end_fragments: tuple[str, ...] = ()
    runtime_config: Mapping[str, object] = field(default_factory=dict)


def render_index_string(
    *,
    application_id: str,
    display_name: str,
    version: str,
    definition: IndexPageDefinition,
    module_contributions: Iterable[tuple[str, IndexContribution]],
) -> str:
    language = definition.language.strip()
    if not _LANGUAGE_PATTERN.fullmatch(language):
        raise WebDefinitionError('Index language has an invalid format')

    head_fragments = list(definition.head_fragments)
    body_start_fragments = list(definition.body_start_fragments)
    body_end_fragments = list(definition.body_end_fragments)
    module_runtime: dict[str, object] = {}

    for module_name, contribution in module_contributions:
        head_fragments.extend(contribution.head_fragments)
        body_start_fragments.extend(contribution.body_start_fragments)
        body_end_fragments.extend(contribution.body_end_fragments)
        if contribution.runtime_config:
            module_runtime[module_name] = dict(contribution.runtime_config)

    _validate_fragments(head_fragments)
    _validate_fragments(body_start_fragments)
    _validate_fragments(body_end_fragments)

    runtime_config = {
        'application': {
            'id': application_id,
            'name': display_name,
            'version': version,
        },
        'public': dict(definition.runtime_config),
        'modules': module_runtime,
    }
    runtime_json = _serialize_runtime_config(runtime_config)

    return '\n'.join(
        (
            '<!DOCTYPE html>',
            f'<html lang="{language}">',
            '<head>',
            '    {%metas%}',
            '    <title>{%title%}</title>',
            '    {%favicon%}',
            '    {%css%}',
            *_indent(head_fragments),
            '</head>',
            '<body>',
            *_indent(body_start_fragments),
            '    {%app_entry%}',
            *_indent(body_end_fragments),
            (
                '    <script id="atlanticus-runtime-config" type="application/json">'
                f'{runtime_json}</script>'
            ),
            '    <footer>',
            '        {%config%}',
            '        {%scripts%}',
            '        {%renderer%}',
            '    </footer>',
            '</body>',
            '</html>',
        )
    )


def _validate_fragments(fragments: Iterable[str]) -> None:
    if any(not isinstance(fragment, str) for fragment in fragments):
        raise WebDefinitionError('Index fragments must be strings')


def _serialize_runtime_config(config: Mapping[str, object]) -> str:
    try:
        serialized = json.dumps(config, ensure_ascii=False, separators=(',', ':'))
    except (TypeError, ValueError) as error:
        raise WebDefinitionError('Runtime configuration must be JSON serializable') from error
    return serialized.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


def _indent(fragments: Iterable[str]) -> tuple[str, ...]:
    return tuple(f'    {fragment}' for fragment in fragments)
