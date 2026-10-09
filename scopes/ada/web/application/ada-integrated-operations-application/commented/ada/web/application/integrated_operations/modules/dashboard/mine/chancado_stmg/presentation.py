from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.ui.feeder import FeederValues
from ada.web.ui.stockpile import StockpileValues, build_stockpile_component

from .correas_stmg import CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC, build_correas_stmg
from .correas_stmg.models import CorreasStmgState
from .equipos_ch import build_equipos_ch
from .equipos_ch.models import EquiposChReading
from .feeders import FEEDERS_CH_DEFINITIONS, build_chancado_feeders
from .leyes import build_leyes_summary
from .leyes.models import LeyesState
from .produccion_global import build_produccion_global
from .produccion_global.models import ProduccionGlobalState
from .stockpile_mina import STOCKPILE_MINA_DEFINITIONS


# Este archivo es la única composición visual de CHANCADO-STMG.
# Recibe estados ya mapeados y mantiene inalterado el orden de seis bloques.
def build_chancado_stmg(
    *,
    produccion_global: ProduccionGlobalState,
    equipos_ch: Sequence[EquiposChReading],
    stockpile_mina: Sequence[StockpileValues],
    feeders: Sequence[FeederValues],
    correas_stmg: CorreasStmgState,
    leyes: LeyesState,
) -> Component:
    # Stockpile utiliza un componente de UI genérico que necesita sus definiciones.
    piles = [
        build_stockpile_component(definition, reading)
        for definition, reading in zip(STOCKPILE_MINA_DEFINITIONS, stockpile_mina, strict=True)
    ]
    # Todos los elementos Dash, incluidos los contenedores, se construyen aquí.
    return html.Div(
        [
            build_produccion_global(produccion_global),
            build_equipos_ch(equipos_ch),
            html.Div(
                [
                    html.Div('Stockpile Mina', className='ada-io-stockpile__title'),
                    html.Div(piles, className='ada-io-stockpile-piles'),
                ],
                className='ada-io-stockpile',
            ),
            build_chancado_feeders(FEEDERS_CH_DEFINITIONS, feeders),
            build_correas_stmg(CORREAS_STMG_DEFINITIONS, CORREAS_STMG_METRIC, correas_stmg),
            build_leyes_summary(leyes),
        ],
        className='ada-io-chancado-stmg',
    )
