# Política interna de presentación: no se resuelve desde .env ni desde Tool Configuration.
from __future__ import annotations

# Ambas modalidades comparten tiempos dentro del mismo Modeler, no entre aplicaciones.
CAROUSEL_ROTATION_SECONDS = 90
QUEUE_IN_QUEUE_ROTATION_SECONDS = 120

# La geometría es propia de cada modalidad, no de la configuración del Job.
CAROUSEL_VISIBLE_SLOTS = 6
QUEUE_IN_QUEUE_SLOTS_PER_AREA = 3
