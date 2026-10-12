from __future__ import annotations

from datetime import UTC, datetime

from ada.processes.alarm_modeler.projection import has_semantic_change, project

from .test_projection import alarm, model, source


def _render(values, template='Presión {pressure} bar, límite {limit} bar', *, previous=None):
    item = alarm('pressure')
    item['evaluation']['cause_values'] = values
    config = model('pressure')
    config['alarms'][0]['cause_template'] = template
    return project(
        current=source([item]),
        modeler_configuration=config,
        publication_tool_keys=('tool-a',),
        now=datetime(2026, 10, 11, tzinfo=UTC),
        previous=previous,
    )


def _record(document):
    return document['tools']['tool-a']['alarms']['occ-pressure']


def test_cause_change_is_semantic_without_journal_progress():
    first = _render({'pressure': 125, 'limit': 100})
    second = _render({'pressure': 132, 'limit': 100}, previous=first)
    assert _record(first)['cause_text'] == 'Presión 125 bar, límite 100 bar'
    assert _record(second)['cause_text'] == 'Presión 132 bar, límite 100 bar'
    assert second['source_journal_position'] == first['source_journal_position']
    assert has_semantic_change(first, second)
    assert 'cause_values' not in _record(second)['evaluation']
    assert 'cause_template' not in _record(second)
    assert second['schema_version'] == 3


def test_same_rendered_cause_does_not_change_live():
    first = _render({'pressure': 125, 'limit': 100})
    second = _render({'pressure': 125, 'limit': 100, 'unused': 999}, previous=first)
    assert not has_semantic_change(first, second)


def test_missing_none_and_invalid_placeholder_keep_full_literal():
    template = 'Presión {pressure} bar, límite {limit} bar'
    for values in ({'pressure': 125}, {'pressure': 125, 'limit': None}, {}):
        assert _record(_render(values))['cause_text'] == template
    assert _record(_render({'pressure': 125}, '{pressure.__class__}'))['cause_text'] == '{pressure.__class__}'
    assert _record(_render({'pressure': 125}, 'Presión {pressure:.2f}'))['cause_text'] == 'Presión 125.00'


def test_literal_static_template_remains_usable_without_values():
    result = _render({}, 'Alarma de presión')
    assert _record(result)['cause_text'] == 'Alarma de presión'
