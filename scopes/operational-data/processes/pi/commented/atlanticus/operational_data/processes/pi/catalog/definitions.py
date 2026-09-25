# Espejo del catálogo productivo PI Web API.
# Las definiciones productivas permanecen vacías hasta que el proceso reciba una configuración explícita.
# Para ejemplos de tags y combinaciones, consultar catalog/_definitions.example.py.

from atlanticus.integrations.pi.contracts import PiTagDefinition, PiWebApiSource

SOURCE = PiWebApiSource(interpolation_seconds=10)

DEFINITIONS: tuple[PiTagDefinition, ...] = ()
