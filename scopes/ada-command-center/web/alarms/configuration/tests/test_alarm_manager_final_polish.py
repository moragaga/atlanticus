from ada_command_center.web.alarms.configuration.web.families import (
    FamilySummary,
    initial_navigation,
)
from ada_command_center.web.alarms.configuration.web.family_panel import (
    _family_listing,
    _rule_subtitle,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    FAMILY_REMOVE_TYPE,
    FAMILY_SELECT_TYPE,
)
from ada_command_center.web.alarms.configuration.web.pagination import change_list_page


def test_family_cards_use_separate_internal_actions_with_correct_page_index():
    families = tuple(FamilySummary(f'family-{number:02d}', (), ()) for number in range(15))
    navigation = change_list_page(initial_navigation(), 'families', page=2)
    listing = _family_listing(families, [], navigation)
    card = listing.children[1].children[0]
    assert card.className == 'alarm-family__item alarm-family__item--card'
    assert card.children[0].children[0].children == 'family-10'
    actions = card.children[1].children
    assert [button.children for button in actions] == ['Administrar', 'Eliminar']
    assert actions[0].id == {'type': FAMILY_SELECT_TYPE, 'index': 10}
    assert actions[1].id == {'type': FAMILY_REMOVE_TYPE, 'key': 'family-10'}


def test_rule_list_subtitle_identifies_priority_group_and_rank():
    rule = {
        'kind': 'IMPACT',
        'criticality': 'C2',
        'is_active': True,
        'priority_group': 'crusher-priority',
        'priority_order': 2,
    }
    description = _rule_subtitle(rule)
    assert 'Grupo: crusher-priority' in description
    assert 'Ranking: 2' in description
    assert description.startswith('Impacto · C2 · Activa')


def test_unassigned_ranking_is_not_invented():
    description = _rule_subtitle({'priority_group': ' ', 'priority_order': None})
    assert 'Grupo: Sin grupo' in description
    assert 'Ranking: Sin orden' in description
