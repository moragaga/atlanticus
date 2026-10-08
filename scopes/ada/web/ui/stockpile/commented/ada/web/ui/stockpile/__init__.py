# Expone únicamente la API actual de Stockpile y su módulo de assets.
# Equivalente al archivo productivo, con explicación pedagógica en español.
from .models import StockpileDefinition, StockpileValues, StockpileVariant
from .module import ADA_STOCKPILE_ASSET_LAYER, create_ada_stockpile_module
from .presentation import build_stockpile_component

__all__ = [
    'ADA_STOCKPILE_ASSET_LAYER',
    'StockpileDefinition',
    'StockpileValues',
    'StockpileVariant',
    'build_stockpile_component',
    'create_ada_stockpile_module',
]
