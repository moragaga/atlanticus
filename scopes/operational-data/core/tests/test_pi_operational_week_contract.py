from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    OperationalScope,
)


def test_pi_week_scopes_reuse_existing_daily_partition() -> None:
    for source in (DataSource.PI_INTERPOLATED, DataSource.PI_RECORDED):
        for scope in (
            OperationalScope.CURRENT_OPERATIONAL_WEEK_MINE,
            OperationalScope.CURRENT_OPERATIONAL_WEEK_PLANT,
        ):
            requirement = DataRequirement(
                source=source,
                partition=DataPartition.DAILY,
                columns=(DataColumn('temperature', DataColumnType.FLOAT),),
                operational_scope=scope,
            )
            assert requirement.partition is DataPartition.DAILY
            assert requirement.operational_scope is scope
