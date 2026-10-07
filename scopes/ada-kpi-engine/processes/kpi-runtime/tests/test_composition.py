from __future__ import annotations

from ada.kpis.core import KpiArea, KpiCatalog, KpiMode, KpiSpec
from ada.processes.kpi_runtime.composition import build_composition
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    OperationalScope,
)
from atlanticus.operational_data.sources import FabricaKpis, FabricaPlanes, PiInterpolated


def _configuration(tmp_path, *, reprocess_current='false') -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-runtime-local',
        'VOLUMEN_PATH': str(tmp_path),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'operational-data-notpii-local',
        'FABRICA_PLANES_APPLICATION': 'operational-data-fabrica-planes-local',
        'FABRICA_KPIS_APPLICATION': 'operational-data-fabrica-kpis-local',
        'KPI_POLL_INTERVAL_SECONDS': '1',
        'REPROCESS_CURRENT': reprocess_current,
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'off',
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_composition_uses_job_runtime_and_empty_catalog(tmp_path) -> None:
    composition = build_composition(
        configuration=_configuration(tmp_path),
        catalog=KpiCatalog(()),
    )

    assert composition.definition.module_name == 'ada.processes.kpi_runtime'
    assert composition.definition.service_name == 'kpi-runtime'
    assert composition.definition.job_key == 'kpi-runtime'
    assert composition.definition.sleep_seconds == 1
    assert composition.definition.iteration_timeout_seconds == 580
    assert composition.definition.execution_timeout_seconds == 600
    assert composition.settings.reprocess_current is False
    assert len(composition.catalog) == 0


def test_composition_accepts_input_based_catalog(tmp_path) -> None:
    spec = KpiSpec(
        key='test-kpi',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        inputs=(
            PiInterpolated.latest(
                input_key='value',
                columns=(DataColumn('signal', DataColumnType.FLOAT),),
            ),
        ),
    )
    composition = build_composition(
        configuration=_configuration(tmp_path),
        catalog=KpiCatalog((spec,)),
    )

    assert composition.catalog.specs == (spec,)
    assert composition.job is not None


def test_composition_accepts_month_partitioned_fabrica_inputs(tmp_path) -> None:
    plans = KpiSpec(
        key='plans-kpi',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        inputs=(
            FabricaPlanes.daily(
                input_key='plans',
                columns=(DataColumn('plan', DataColumnType.FLOAT),),
                period=OperationalScope.CURRENT_OPERATIONAL_DAY_PLANT,
            ),
        ),
    )
    kpis = KpiSpec(
        key='fabrica-kpi',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        inputs=(
            FabricaKpis.weekly(
                input_key='weekly',
                columns=(DataColumn('actual', DataColumnType.FLOAT),),
                period=OperationalScope.CURRENT_OPERATIONAL_WEEK_PLANT,
            ),
        ),
    )

    composition = build_composition(
        configuration=_configuration(tmp_path),
        catalog=KpiCatalog((plans, kpis)),
    )

    assert composition.catalog.specs == (plans, kpis)
    assert composition.settings.fabrica_planes_application == (
        'operational-data-fabrica-planes-local'
    )
    assert composition.settings.fabrica_kpis_application == ('operational-data-fabrica-kpis-local')


def test_composition_accepts_reprocess_current_enabled(tmp_path) -> None:
    composition = build_composition(
        configuration=_configuration(tmp_path, reprocess_current='true'),
        catalog=KpiCatalog(()),
    )

    assert composition.settings.reprocess_current is True
