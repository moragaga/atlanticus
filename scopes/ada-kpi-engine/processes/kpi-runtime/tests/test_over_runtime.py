from ada.kpis.core import KpiArea, KpiCatalog, KpiValueType, OverKpiSpec
from ada.processes.kpi_runtime.job import KpiRuntimeJob
from tests.support import (
    RuntimeContextStub,
    StaticWatermarkReader,
    runtime_parts,
    simple_catalog,
    watermark,
)


def test_runtime_evaluates_base_then_over_into_same_durable_batch(tmp_path):
    base_catalog = simple_catalog()
    over = OverKpiSpec(
        key='general.double',
        area=KpiArea.GENERAL,
        dependencies=('test-kpi',),
        resolver=lambda values: values['test-kpi'] * 2,
        value_type=KpiValueType.FLOAT,
        decimals=1,
        persist_history=True,
    )
    catalog = KpiCatalog(base_catalog.specs, (over,))
    catalog, plan, loader, persistence, reader = runtime_parts(tmp_path, catalog=catalog)
    job = KpiRuntimeJob(
        catalog=catalog,
        plan=plan,
        loader=loader,
        persistence=persistence,
        source_watermarks=StaticWatermarkReader(watermark(1)),
    )

    result = job.run_iteration(RuntimeContextStub())
    batches = persistence.read_committed_after()

    assert result.evaluation_count == 2
    assert reader.calls == 1
    assert len(batches) == 1
    by_key = {evaluation.key: evaluation for evaluation in batches[0].evaluations}
    assert by_key['test-kpi'].value == '42.5'
    assert by_key['test-kpi'].parsed_value == '42,5'
    assert by_key['general.double'].value == '85.0'
    assert by_key['general.double'].parsed_value == '85,0'
    assert by_key['general.double'].persist_history is True


def test_over_kpi_does_not_add_operational_data_requirements(tmp_path):
    base_catalog = simple_catalog()
    over = OverKpiSpec(
        key='general.copy',
        area=KpiArea.GENERAL,
        dependencies=('test-kpi',),
        resolver=lambda values: values['test-kpi'],
        value_type=KpiValueType.FLOAT,
        decimals=1,
    )
    catalog = KpiCatalog(base_catalog.specs, (over,))
    _, plan, _, _, _ = runtime_parts(tmp_path, catalog=catalog)

    assert tuple(plan.requirements_by_key) == ('test-kpi',)
