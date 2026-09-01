# Expone únicamente el constructor estable del catálogo; definitions.py queda
# como frontera declarativa.
from atlanticus.operational_data.processes.pi.catalog.provider import build_catalog

__all__ = ['build_catalog']
