# Punto de entrada mínimo: delega todo el bootstrap al módulo estable del proceso.
# No compone dependencias ni lee configuración aquí para mantener una única ruta de arranque.
from atlanticus.operational_data.processes.pi.bootstrap import main

main()
