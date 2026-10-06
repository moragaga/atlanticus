from dash import html

from ada.web.ui.card_display import build_card_display, build_card_display_region


def _class_node(component, class_name: str):
    for child in component.children:
        if getattr(child, 'className', None) == class_name:
            return child
    raise AssertionError(f'Class not found: {class_name}')


def test_card_display_uses_projection_binding_without_deriving_another_id() -> None:
    card = build_card_display(
        component_key='molienda',
        wrapper_id='ada-runtime-component-molienda',
        content=html.Div('content'),
    )

    assert card.id == 'ada-runtime-component-molienda'
    assert getattr(card, 'data-ada-component-key') == 'molienda'
    assert card.className == 'ada-card-display'
    assert card.to_plotly_json()['type'] == 'Article'


def test_card_display_projects_optional_subcomponent_identity() -> None:
    card = build_card_display(
        component_key='carguio',
        subcomponent_key='gestion_carguio_turno',
        wrapper_id='ada-runtime-subcomponent-carguio-gestion-carguio-turno',
    )

    assert getattr(card, 'data-ada-component-key') == 'carguio'
    assert getattr(card, 'data-ada-subcomponent-key') == 'gestion_carguio_turno'


def test_card_display_projects_linked_component_identity_without_deriving_keys() -> None:
    card = build_card_display(
        component_key='carguio',
        subcomponent_key='gestion_carguio_turno',
        linked_component_keys=('transporte', 'chancado_stmg'),
        wrapper_id='shared-card',
    )

    assert getattr(card, 'data-ada-linked-component-keys') == 'transporte chancado_stmg'


def test_card_display_materializes_canonical_content_regions_footer_and_overlay_slots() -> None:
    region = build_card_display_region(
        subcomponent_key='sag',
        wrapper_id='ada-runtime-subcomponent-molienda-sag',
        children=html.Div('region'),
    )
    overlay = html.Div('external state', id='external-overlay')
    card = build_card_display(
        component_key='molienda',
        wrapper_id='ada-runtime-component-molienda',
        content=html.Div('content'),
        regions=(region,),
        footer=html.Div('footer'),
        overlay=overlay,
    )

    assert [child.className for child in card.children] == [
        'ada-card-display__content',
        'ada-card-display__regions',
        'ada-card-display__footer',
        'ada-card-display__overlay',
    ]
    assert _class_node(card, 'ada-card-display__overlay').children == [overlay]


def test_region_uses_subcomponent_binding_without_reconstructing_it() -> None:
    region = build_card_display_region(
        subcomponent_key='sag',
        wrapper_id='projection-owned-wrapper-id',
        children='value',
    )

    assert region.id == 'projection-owned-wrapper-id'
    assert getattr(region, 'data-ada-subcomponent-key') == 'sag'
    assert region.children == ['value']


def test_card_display_accepts_sequence_and_scalar_children_without_string_expansion() -> None:
    card = build_card_display(
        component_key='component_a',
        wrapper_id='component-wrapper',
        content='abc',
        footer=('left', 'right'),
    )

    assert _class_node(card, 'ada-card-display__content').children == ['abc']
    assert _class_node(card, 'ada-card-display__footer').children == ['left', 'right']


def test_card_display_preserves_custom_classes_without_replacing_base_classes() -> None:
    region = build_card_display_region(
        subcomponent_key='sub_a',
        wrapper_id='sub-wrapper',
        class_name='custom-region',
    )
    card = build_card_display(
        component_key='component_a',
        wrapper_id='component-wrapper',
        class_name='custom-card',
        regions=region,
    )

    assert card.className == 'ada-card-display custom-card'
    assert region.className == 'ada-card-display__region custom-region'


def test_card_display_rejects_empty_projection_wrapper_id() -> None:
    try:
        build_card_display(component_key='component_a', wrapper_id=' ')
    except ValueError as error:
        assert str(error) == 'Card Display wrapper_id must be a non-empty string'
    else:
        raise AssertionError('Expected ValueError')


def test_card_display_reuses_core_subcomponent_key_validation() -> None:
    try:
        build_card_display(
            component_key='component_a',
            subcomponent_key='Invalid-Key',
            wrapper_id='wrapper',
        )
    except ValueError as error:
        assert 'Invalid ADA DOM subcomponent key' in str(error)
    else:
        raise AssertionError('Expected ValueError')


def test_card_display_reuses_core_validation_for_linked_component_keys() -> None:
    try:
        build_card_display(
            component_key='component_a',
            linked_component_keys=('Invalid-Key',),
            wrapper_id='wrapper',
        )
    except ValueError as error:
        assert 'Invalid ADA DOM component key' in str(error)
    else:
        raise AssertionError('Expected ValueError')


def test_card_display_rejects_scalar_linked_component_keys() -> None:
    try:
        build_card_display(
            component_key='component_a',
            linked_component_keys='component_b',
            wrapper_id='wrapper',
        )
    except TypeError as error:
        assert str(error) == (
            'Card Display linked_component_keys must be a sequence of component keys'
        )
    else:
        raise AssertionError('Expected TypeError')


def test_region_reuses_core_subcomponent_key_validation() -> None:
    try:
        build_card_display_region(subcomponent_key='Invalid-Key', wrapper_id='wrapper')
    except ValueError as error:
        assert 'Invalid ADA DOM subcomponent key' in str(error)
    else:
        raise AssertionError('Expected ValueError')
