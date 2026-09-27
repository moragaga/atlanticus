# Punto de entrada para python -m; delega en el mismo bootstrap que usan los demás procesos.
from ada_command_center.processes.alarms_materialization.bootstrap import main

if __name__ == '__main__':
    main()
