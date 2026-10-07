# Azure Container Apps — recursos de procesos

`deployment.resources.json` define los recursos efectivos usados para probar los procesos de esta distribución en Docker.

El archivo pertenece al consumidor de la distribución. Puede editarse sin modificar `pyproject.toml`, `compose.yaml`, `.env` ni `config.json`. Los comandos locales leen el archivo en cada ejecución, por lo que no existe un paso de sincronización.

## Combinaciones admitidas

| vCPU | RAM (GiB) | Docker |
| ---: | ---: | ---: |
| 0.25 | 0.5 | 512m |
| 0.50 | 1.0 | 1024m |
| 0.75 | 1.5 | 1536m |
| 1.00 | 2.0 | 2048m |
| 1.25 | 2.5 | 2560m |
| 1.50 | 3.0 | 3072m |
| 1.75 | 3.5 | 3584m |
| 2.00 | 4.0 | 4096m |
| 2.25 | 4.5 | 4608m |
| 2.50 | 5.0 | 5120m |
| 2.75 | 5.5 | 5632m |
| 3.00 | 6.0 | 6144m |
| 3.25 | 6.5 | 6656m |
| 3.50 | 7.0 | 7168m |
| 3.75 | 7.5 | 7680m |
| 4.00 | 8.0 | 8192m |

La relación admitida es `RAM GiB = vCPU × 2`, con vCPU entre `0.25` y `4.0` en incrementos de `0.25`.

Para Docker, Atlanticus traduce la memoria con `MiB = RAM GiB × 1024`. Por ejemplo, `1.5 vCPU / 3.0 GiB` se ejecuta localmente con `--cpus 1.5 --memory 3072m`.

## Configuración

Ejemplo:

```json
{
  "schema_version": 1,
  "processes": {
    "pi-web-api": {
      "vcpu": 0.5,
      "memory_gib": 1.0
    },
    "kpis-runtime": {
      "vcpu": 1.5,
      "memory_gib": 3.0
    }
  }
}
```

Todos los procesos instalados deben aparecer exactamente una vez. Una combinación fuera de la tabla bloquea `validate`, `up`, `run` y `simulate` antes de iniciar el proceso.

El default al agregar un proceso nuevo es `0.5 vCPU / 1.0 GiB`. Una regeneración conserva los valores ya definidos para los procesos que permanecen en la distribución.

Esta tabla es el perfil de recursos aceptado por el tooling de Atlanticus para pruebas locales representativas. La disponibilidad final debe validarse contra el entorno Azure donde se desplegará la aplicación.
