# Migración de BirdMonitor a múltiples ubicaciones

Esta carpeta centraliza los informes de cada fase necesaria para que un mismo nodo físico pueda conservar y consultar datos independientes de Sevilla, Algeciras, Sangüesa y futuras ubicaciones.

La solución mantiene una sola base de datos física. La separación se realiza de forma lógica mediante dos conceptos distintos:

- **sitio**: lugar geográfico estable en el que se realizan observaciones;
- **despliegue**: periodo durante el cual un nodo concreto está instalado en un sitio.

## Informes

| Fase | Estado | Informe |
|---|---|---|
| 0. Congelación y auditoría | Completada | [fase_0_congelacion_y_auditoria.md](fase_0_congelacion_y_auditoria.md) |
| 1. Diseño de sitios y despliegues | Completada | [fase_1_diseno_sitios_y_despliegues.md](fase_1_diseno_sitios_y_despliegues.md) |
| 2. Esquema y migración de datos | Completada | [fase_2_esquema_y_migracion.md](fase_2_esquema_y_migracion.md) |
| 3. API por ubicación | Completada | [fase_3_api_y_filtrado_por_ubicacion.md](fase_3_api_y_filtrado_por_ubicacion.md) |
| 4. Configuración de la Raspberry Pi | Pendiente | — |
| 5. Dashboard histórico por ubicación | Pendiente | — |
| 6. Pruebas de aislamiento y seguridad | Pendiente | — |
| 7. Despliegue de Algeciras | Pendiente | — |
| 8. Validación y operación | Pendiente | — |

Los respaldos binarios, inventarios y hashes permanecen fuera de esta carpeta documental, dentro de `backend/app/backups`, para no confundir informes con artefactos de recuperación.

El incidente de aislamiento de pruebas detectado y recuperado durante la Fase 3 se documenta por separado en [incidente_aislamiento_pytest_fase_3.md](incidente_aislamiento_pytest_fase_3.md).
