from ada.alarms.materialization import (
    delivery_from_document,
    delivery_to_document,
    engine_from_document,
    engine_to_document,
    modeler_from_document,
    modeler_to_document,
)

from .support import delivery_configuration, engine_configuration, modeler_configuration


def test_three_materialized_configurations_round_trip() -> None:
    engine = engine_configuration()
    modeler = modeler_configuration()
    delivery = delivery_configuration()

    assert engine_from_document(engine_to_document(engine)) == engine
    assert modeler_from_document(modeler_to_document(modeler)) == modeler
    assert delivery_from_document(delivery_to_document(delivery)) == delivery


def test_engine_codec_preserves_special_condition_flag() -> None:
    engine = engine_configuration(is_special_condition=True)
    document = engine_to_document(engine)

    assert document['planned_alarms'][0]['is_special_condition'] is True
    assert engine_from_document(document) == engine
