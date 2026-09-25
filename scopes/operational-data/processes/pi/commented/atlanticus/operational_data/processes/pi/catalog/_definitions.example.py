# Espejo pedagógico del catálogo de ejemplo del proceso PI.
# Este ejemplo no se incorpora al catálogo productivo; definitions.py permanece vacío.
# INTERPOLATED admite LATEST, DAILY y MONTHLY; RECORDED admite DAILY y MONTHLY.
# REAL EXAMPLE representa tres tags de ejemplo existentes, no referencias obligatorias.
# FAKE EXAMPLES demuestra las combinaciones admitidas por contrato.
from atlanticus.integrations.pi.contracts import (
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
    PiWebApiSource,
)

EXAMPLE_SOURCE = PiWebApiSource(interpolation_seconds=10)

EXAMPLE_DEFINITIONS = (
    # REAL EXAMPLE
    PiTagDefinition(
        tag_name='ML001ARUN',
        alias='estado_sag_1_inst',
        value_kind=PiValueKind.TEXT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST,),
    ),
    PiTagDefinition(
        tag_name='320:L1.F80(INCH)',
        alias='f80_sag_1_inst',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.DAILY,),
    ),
    PiTagDefinition(
        tag_name='330:RECCU_AJUST.H',
        alias='recuperacion_ajustada_hora_inst',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.MONTHLY,),
    ),
    # FAKE EXAMPLES
    PiTagDefinition(
        tag_name='INTERPOLATED_LATEST_TAG',
        alias='interpolated_latest',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST,),
    ),
    PiTagDefinition(
        tag_name='INTERPOLATED_DAILY_TAG',
        alias='interpolated_daily',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.DAILY,),
    ),
    PiTagDefinition(
        tag_name='INTERPOLATED_MONTHLY_TAG',
        alias='interpolated_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.MONTHLY,),
    ),
    PiTagDefinition(
        tag_name='INTERPOLATED_LATEST_DAILY_TAG',
        alias='interpolated_latest_daily',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST, PiMaterialization.DAILY),
    ),
    PiTagDefinition(
        tag_name='INTERPOLATED_LATEST_MONTHLY_TAG',
        alias='interpolated_latest_monthly',
        value_kind=PiValueKind.TEXT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST, PiMaterialization.MONTHLY),
    ),
    PiTagDefinition(
        tag_name='INTERPOLATED_DAILY_MONTHLY_TAG',
        alias='interpolated_daily_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.DAILY, PiMaterialization.MONTHLY),
    ),
    PiTagDefinition(
        tag_name='INTERPOLATED_LATEST_DAILY_MONTHLY_TAG',
        alias='interpolated_latest_daily_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(
            PiMaterialization.LATEST,
            PiMaterialization.DAILY,
            PiMaterialization.MONTHLY,
        ),
    ),
    PiTagDefinition(
        tag_name='RECORDED_DAILY_TAG',
        alias='recorded_daily',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.DAILY,),
    ),
    PiTagDefinition(
        tag_name='RECORDED_MONTHLY_TAG',
        alias='recorded_monthly',
        value_kind=PiValueKind.TEXT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.MONTHLY,),
    ),
    PiTagDefinition(
        tag_name='RECORDED_DAILY_MONTHLY_TAG',
        alias='recorded_daily_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.DAILY, PiMaterialization.MONTHLY),
    ),
)
