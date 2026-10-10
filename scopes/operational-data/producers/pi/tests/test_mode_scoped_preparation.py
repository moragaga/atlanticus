from types import SimpleNamespace

from atlanticus.data_producers.pi import PiExecutionPlanPreparer, WebIdRegistry
from atlanticus.integrations.pi.contracts import (
    PiCatalog,
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
    PiWebApiSource,
)
from atlanticus.integrations.pi.web_api import PiPointWebIdResult, PiWebApiLimits


class FakePoints:
    def __init__(self, web_ids: dict[str, str]) -> None:
        self.web_ids = web_ids
        self.calls: list[tuple[str, ...]] = []

    def resolve_web_ids(self, tag_names: tuple[str, ...]) -> tuple[PiPointWebIdResult, ...]:
        self.calls.append(tag_names)
        return tuple(
            PiPointWebIdResult(
                tag_name=name,
                path=f'\\PISERVER\\{name}',
                point_name=name if name in self.web_ids else None,
                web_id=self.web_ids.get(name),
                error=None if name in self.web_ids else 'Point not found',
            )
            for name in tag_names
        )


class FakeClient:
    def __init__(self, web_ids: dict[str, str]) -> None:
        self.points = FakePoints(web_ids)
        self.settings = SimpleNamespace(limits=PiWebApiLimits())


def _catalog(recorded_name: str = 'TAG_A') -> PiCatalog:
    return PiCatalog(
        source=PiWebApiSource(interpolation_seconds=10),
        definitions=(
            PiTagDefinition(
                tag_name='TAG_A',
                alias='same',
                value_kind=PiValueKind.FLOAT,
                extraction_mode=PiExtractionMode.INTERPOLATED,
                materializations=(PiMaterialization.LATEST,),
            ),
            PiTagDefinition(
                tag_name=recorded_name,
                alias='same',
                value_kind=PiValueKind.FLOAT,
                extraction_mode=PiExtractionMode.RECORDED,
                materializations=(PiMaterialization.DAILY,),
            ),
        ),
    )


def test_shared_pi_tag_resolves_web_id_once_and_keeps_both_modes(tmp_path) -> None:
    client = FakeClient({'TAG_A': 'WEB_A'})
    registry = WebIdRegistry(path=tmp_path / 'webids.json')

    result = PiExecutionPlanPreparer(client=client, registry=registry).prepare(_catalog())

    assert client.points.calls == [('TAG_A',)]
    assert result.point_request_count == 1
    assert result.resolved_count == 1
    assert result.unresolved_count == 0
    assert result.plan.interpolated[0].web_id == 'WEB_A'
    assert result.plan.recorded[0].web_id == 'WEB_A'
    assert len(result.plan.by_name) == 2


def test_shared_pi_tag_reuses_cached_web_id_for_both_modes(tmp_path) -> None:
    registry = WebIdRegistry(path=tmp_path / 'webids.json')
    registry.merge({'TAG_A': 'WEB_A'})
    client = FakeClient({})

    result = PiExecutionPlanPreparer(client=client, registry=registry).prepare(_catalog())

    assert client.points.calls == []
    assert result.cache_hit_count == 1
    assert result.resolved_count == 0
    assert len(result.plan.resolved) == 2


def test_shared_pi_tag_unresolved_is_reported_once(tmp_path) -> None:
    client = FakeClient({})
    registry = WebIdRegistry(path=tmp_path / 'webids.json')

    result = PiExecutionPlanPreparer(client=client, registry=registry).prepare(_catalog())

    assert client.points.calls == [('TAG_A',)]
    assert result.unresolved_count == 1
    assert result.plan.unresolved_tag_names == ('TAG_A',)
    assert result.plan.resolved == ()


def test_case_variation_between_modes_reuses_single_web_id(tmp_path) -> None:
    client = FakeClient({'TAG_A': 'WEB_A'})
    registry = WebIdRegistry(path=tmp_path / 'webids.json')

    result = PiExecutionPlanPreparer(client=client, registry=registry).prepare(_catalog('tag_a'))

    assert client.points.calls == [('TAG_A',)]
    assert result.plan.interpolated[0].tag_name == 'TAG_A'
    assert result.plan.recorded[0].tag_name == 'tag_a'
    assert result.plan.recorded[0].web_id == 'WEB_A'
