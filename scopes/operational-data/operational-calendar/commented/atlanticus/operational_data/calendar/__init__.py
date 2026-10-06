# Este módulo expone únicamente la API pública estable del calendario operacional del scope.
# Los comentarios explican intención y fronteras sin modificar estructura ni comportamiento.

from atlanticus.operational_data.calendar.calendar import (
    DAY_TURN,
    DEFAULT_OPERATIONAL_WEEK_START_WEEKDAY,
    DEFAULT_TIMEZONE_NAME,
    MINE_CALENDAR,
    NIGHT_TURN,
    OPERATIONAL_CALENDARS,
    PLANT_CALENDAR,
    OperationalCalendar,
)
from atlanticus.operational_data.calendar.contracts import OperationalCalendarResolver
from atlanticus.operational_data.calendar.dispatch import (
    SHIFT_ID_TURN_WINDOW_SIZE,
    get_current_shift_id_turn,
    get_previous_shift_id_turn,
    get_shift_id_turn_window,
    parse_shift_id_turn,
)
from atlanticus.operational_data.calendar.groups import (
    TurnArea,
    TurnCalendarResult,
    build_turn_calendar_rows,
    get_current_turn,
    get_previous_turn,
    get_turns_for_incremental_window,
)
from atlanticus.operational_data.calendar.models import (
    OperationalDayWindow,
    OperationalWeekPartition,
    OperationalWeekWindow,
    ShiftIdTurn,
    WorkShiftCode,
    WorkShiftWindow,
)

__version__ = '1.0.0'

__all__ = [
    'OPERATIONAL_CALENDARS',
    'DAY_TURN',
    'DEFAULT_OPERATIONAL_WEEK_START_WEEKDAY',
    'DEFAULT_TIMEZONE_NAME',
    'MINE_CALENDAR',
    'NIGHT_TURN',
    'OperationalCalendar',
    'OperationalCalendarResolver',
    'OperationalDayWindow',
    'OperationalWeekPartition',
    'OperationalWeekWindow',
    'PLANT_CALENDAR',
    'SHIFT_ID_TURN_WINDOW_SIZE',
    'ShiftIdTurn',
    'TurnArea',
    'TurnCalendarResult',
    'WorkShiftCode',
    'WorkShiftWindow',
    '__version__',
    'build_turn_calendar_rows',
    'get_current_shift_id_turn',
    'get_current_turn',
    'get_previous_shift_id_turn',
    'get_previous_turn',
    'get_shift_id_turn_window',
    'get_turns_for_incremental_window',
    'parse_shift_id_turn',
]
