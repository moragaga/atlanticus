# Espejo pedagógico de los contratos puros compartidos de datos operacionales.
from atlanticus.operational_data.core.contracts import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
    DataSourceView,
    OperationalScope,
    ShiftScope,
    ShiftSelection,
    TimeWindow,
    TimeWindowUnit,
    normalize_utc_second,
)
from atlanticus.operational_data.core.errors import (
    DataColumnNotRequestedError,
    DataInputNotRequestedError,
    DataSourceNotRequestedError,
)
from atlanticus.operational_data.core.inputs import (
    DataInputSpec,
    DataSelection,
    DataView,
    OperationalScopeSelection,
    TimeWindowSelection,
    validate_data_inputs,
)
from atlanticus.operational_data.core.runtime import (
    DataInputContext,
    DataRuntimeContext,
    RuntimeFrameContext,
)

__version__ = '1.0.0'

__all__ = [
    'DataColumn',
    'DataColumnNotRequestedError',
    'DataColumnType',
    'DataInputContext',
    'DataInputNotRequestedError',
    'DataInputSpec',
    'DataPartition',
    'DataRequirement',
    'DataRuntimeContext',
    'DataSelection',
    'DataSource',
    'DataSourceNotRequestedError',
    'DataSourceView',
    'DataView',
    'OperationalScope',
    'OperationalScopeSelection',
    'RuntimeFrameContext',
    'ShiftScope',
    'ShiftSelection',
    'TimeWindow',
    'TimeWindowSelection',
    'TimeWindowUnit',
    '__version__',
    'normalize_utc_second',
    'validate_data_inputs',
]
