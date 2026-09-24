# Espejo comentado del proceso NOTPII: composición, batch, materialización, estado y settlement.
# Este archivo conserva exactamente el comportamiento productivo y agrega solo contexto.
from atlanticus.integrations.pi.contracts import (
    NotPiiSource,
    PiExtractionMode,
    PiMaterialization,
    PiTagDefinition,
    PiValueKind,
)

SOURCE = NotPiiSource()

DEFINITIONS: tuple[PiTagDefinition, ...] = (
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
        tag_name='TAG_I_01',
        alias='i_latest',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST,),
    ),
    PiTagDefinition(
        tag_name='TAG_I_02',
        alias='i_daily',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.DAILY,),
    ),
    PiTagDefinition(
        tag_name='TAG_I_03',
        alias='i_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.MONTHLY,),
    ),
    PiTagDefinition(
        tag_name='TAG_I_04',
        alias='i_latest_daily',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST, PiMaterialization.DAILY),
    ),
    PiTagDefinition(
        tag_name='TAG_I_05',
        alias='i_latest_monthly',
        value_kind=PiValueKind.TEXT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.LATEST, PiMaterialization.MONTHLY),
    ),
    PiTagDefinition(
        tag_name='TAG_I_06',
        alias='i_daily_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(PiMaterialization.DAILY, PiMaterialization.MONTHLY),
    ),
    PiTagDefinition(
        tag_name='TAG_I_07',
        alias='i_all',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.INTERPOLATED,
        materializations=(
            PiMaterialization.LATEST,
            PiMaterialization.DAILY,
            PiMaterialization.MONTHLY,
        ),
    ),
    PiTagDefinition(
        tag_name='TAG_R_01',
        alias='r_daily',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.DAILY,),
    ),
    PiTagDefinition(
        tag_name='TAG_R_02',
        alias='r_monthly',
        value_kind=PiValueKind.TEXT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.MONTHLY,),
    ),
    PiTagDefinition(
        tag_name='TAG_R_03',
        alias='r_daily_monthly',
        value_kind=PiValueKind.FLOAT,
        extraction_mode=PiExtractionMode.RECORDED,
        materializations=(PiMaterialization.DAILY, PiMaterialization.MONTHLY),
    ),
)

