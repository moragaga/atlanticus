# API publica de lecturas latest reutilizable entre aplicaciones ADA Web.
from .latest import KpiLatestReadings, read_component_latest, read_system_latest

__all__ = ['KpiLatestReadings', 'read_component_latest', 'read_system_latest']
