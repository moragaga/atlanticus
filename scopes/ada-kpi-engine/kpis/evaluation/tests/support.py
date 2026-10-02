from __future__ import annotations

from dataclasses import dataclass

from atlanticus.operational_data.core import DataRuntimeContext, DataSourceView


class Column:
    def __init__(self, values: list[object]) -> None:
        self._values = values

    def tolist(self) -> list[object]:
        return list(self._values)


class Table:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.columns = tuple(rows[0]) if rows else ()

    def __getitem__(self, column: str) -> Column:
        return Column([row[column] for row in self._rows])


@dataclass(frozen=True)
class Frame:
    dataframe: Table

    def last_row(self):
        if not self.dataframe._rows:
            return None
        return self.dataframe._rows[-1]

    def last_value(self, column: str, default=None):
        row = self.last_row()
        if row is None:
            return default
        return row.get(column, default)

    def last_value_number(self, column: str, default=None):
        return self.last_value(column, default)


def context(view: DataSourceView, rows: list[dict[str, object]]) -> DataRuntimeContext:
    return DataRuntimeContext({view: Frame(Table(rows))})
