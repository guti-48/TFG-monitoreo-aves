# Fase 0 — congelación y auditoría previa a la gestión por ubicaciones

Fecha de ejecución: 9 de agosto de 2026  
Proyecto: BirdMonitor  
Objetivo: conservar y verificar el estado anterior a la incorporación de sitios y despliegues, sin migrar ni eliminar información.

## Resultado

La Fase 0 se ha completado sin modificar la base de datos operativa, los WAV ni los espectrogramas. Se dispone de:

- una copia coherente de SQLite creada mediante la API de copia en línea de SQLite;
- una prueba real de restauración sobre un archivo temporal independiente;
- un inventario con SHA-256 de cada WAV conservado;
- un inventario con SHA-256 de cada espectrograma conservado;
- una auditoría de integridad, relaciones, referencias acústicas y duplicados;
- una ejecución completa de las pruebas automatizadas del proyecto.

La Raspberry Pi no intervino en esta fase y puede permanecer desconectada. Será necesaria cuando se implemente y despliegue la selección del sitio activo en el nodo.

## Archivos de recuperación

| Archivo | Finalidad | Tamaño | SHA-256 |
|---|---|---:|---|
| [`birdmonitor.db`](../../backend/app/backups/phase0-location-20260809-193418/birdmonitor.db) | Copia recuperable de la base de datos | 630 784 bytes | `3F91537B8C053BBCCD87C72BE6B06F09B47D406BD660D77C8BC96A4694CAB60F` |
| [`audio_inventory.csv`](../../backend/app/backups/phase0-location-20260809-193418/audio_inventory.csv) | Inventario individual de los WAV | 26 324 bytes | `A66BC99977A52ABC08F1E768C70564A91E4D7AD5EB703961FEF1751377AA00FC` |
| [`spectrogram_inventory.csv`](../../backend/app/backups/phase0-location-20260809-193418/spectrogram_inventory.csv) | Inventario individual de los espectrogramas | 26 139 bytes | `EBDB6FC954D4C208FFBF1AB6662B5225AA30AA947ABA593362E17DCC9B42301B` |
| [`CHECKSUMS.sha256`](../../backend/app/backups/phase0-location-20260809-193418/CHECKSUMS.sha256) | Manifiesto compacto de comprobación | — | — |

Los inventarios contienen, para cada archivo acústico, su ruta relativa, tamaño, fecha de modificación en UTC y SHA-256. Los archivos acústicos no se han duplicado en esta misma unidad porque ocuparían aproximadamente 1,04 GiB y una copia en el mismo disco no protegería frente a un fallo físico. Antes de la migración se recomienda copiar tanto esta carpeta como `hardware/raspberry_pi/records` y `hardware/raspberry_pi/spectrograms` a una unidad distinta.

## Estado congelado de los datos

### Base de datos

| Tabla | Filas | SHA-256 lógico |
|---|---:|---|
| `devices` | 1 | `2f02f92fb1ef88d20443a5884fa4029257cf1eec280245fb03196062c3bcd529` |
| `detections` | 198 | `5114d64cbd1b2561ca10e920193c18cd004bd01ae5eb12cdd452e4626e23e4e0` |
| `detection_reviews` | 174 | `583feb220f378eefd0a3b406cdac435cc2bb521c716240661db81ba9447dc7` |
| `audio_metrics` | 1 168 | `20136f9fd243e9192853ad63264f85f8d2a5ed5eebbe3a9c5374e0f869cabafc` |
| `learning_examples` | 163 | `a2a4cd11f5b1c610e2af6f5bc05308c114e9f746781d722c07c8c43767ba05c2` |
| `learning_rules` | 27 | `b2ce6de5218f6a477a2d5b4f256c654ae5f11ca74d511fc10f6643e5841ee428` |

- `PRAGMA integrity_check`: `ok` en el origen y en la copia.
- Errores de clave foránea: 0 en el origen y en la copia.
- Páginas SQLite: 154 en ambos archivos.
- Las filas y los hashes lógicos de todas las tablas coinciden entre origen y copia.
- Detecciones: desde `2026-05-07 16:36:24.133704` hasta `2026-07-29 16:24:10.900422`.
- Métricas acústicas: desde `2026-05-26 10:01:41.719761` hasta `2026-07-29 16:35:10.994846`.
- 24 detecciones todavía no tienen revisión humana.
- 23 detecciones antiguas no contienen temporización acústica; el sistema actual las admite por compatibilidad.

El único dispositivo registrado es `birdmonitor`, asociado en el estado previo a Sevilla mediante geolocalización. Esta asociación se conservará como procedencia histórica durante la futura migración.

### Archivos acústicos

| Colección | Archivos | Tamaño total | Intervalo observado |
|---|---:|---:|---|
| WAV | 185 | 1 065 608 140 bytes | 2 de mayo — 29 de julio de 2026 |
| Espectrogramas | 185 | 46 543 583 bytes | 2 de mayo — 29 de julio de 2026 |

## Prueba de restauración

La copia `birdmonitor.db` se restauró en una base temporal independiente. El resultado fue:

- SHA-256 restaurado: `3F91537B8C053BBCCD87C72BE6B06F09B47D406BD660D77C8BC96A4694CAB60F`;
- `PRAGMA integrity_check`: `ok`;
- errores de clave foránea: 0;
- detecciones: 198;
- métricas acústicas: 1 168.

La base restaurada es byte a byte idéntica a la copia de seguridad. El archivo temporal de ensayo no forma parte del respaldo definitivo.

## Hallazgos conservados, no corregidos

La Fase 0 documenta estas anomalías pero no las modifica, para no mezclar una migración estructural con una depuración de información científica:

- cuatro grupos de detecciones exactamente duplicadas, con cuatro filas excedentes (identificadores `2/9`, `3/10`, `4/11` y `5/12`);
- un grupo duplicado de métricas acústicas (identificadores `111/112`);
- cuatro referencias históricas a WAV sin extensión, que el resolvedor actual encuentra añadiendo `.wav`;
- dos WAV referenciados que no están presentes: `record_2026-05-07_17-50-43` y `record_2026-05-07_17-59-16`;
- dos pares WAV/espectrograma existentes pero sin detección asociada: `record_2026-05-02_18-58-51` y `record_2026-05-02_19-03-51`;
- ningún espectrograma ausente para los nombres de detección registrados;
- ninguna revisión duplicada por detección y ningún ejemplo de aprendizaje duplicado por detección.

Estos casos deben permanecer inalterados durante la migración. Su depuración, si se decide realizarla, deberá ser una operación separada, reversible y documentada.

## Verificación del software

Se ejecutó la suite disponible antes de introducir cambios de esquema:

```text
80 passed, 1 warning in 27.12s
```

La advertencia corresponde a la detección de `ffmpeg/avconv` por `pydub` en el entorno de pruebas y no produjo fallos.

El backend siguió respondiendo correctamente a `/health` por la interfaz local y por la interfaz Tailscale configurada. El estado devuelto confirmó que el modo de red, la autenticación y la seguridad del streaming estaban configurados.

Se observó que el backend estaba activo como proceso, aunque la tarea programada `BirdMonitor Backend` no figuraba registrada en ese momento. No se detuvo el proceso durante la congelación, ya que la copia en línea de SQLite garantiza coherencia transaccional y detenerlo habría introducido un riesgo operativo innecesario. Conviene normalizar este arranque antes del despliegue final, pero no afecta a la validez de la copia.

## Procedimiento de recuperación

Este procedimiento solo debe ejecutarse si una futura migración falla. No se ha aplicado sobre el sistema operativo:

1. Detener el backend y confirmar que ningún proceso mantiene abierta la base de datos.
2. Mover la base problemática a un nombre fechado de cuarentena; no eliminarla.
3. Comprobar el SHA-256 de `birdmonitor.db` contra `CHECKSUMS.sha256`.
4. Copiar `birdmonitor.db` a `backend/app/birdmonitor.db`.
5. Iniciar el backend y consultar `/health`.
6. Ejecutar `PRAGMA integrity_check` y `PRAGMA foreign_key_check`.
7. Comprobar que existen 198 detecciones y 1 168 métricas acústicas.
8. Si faltan archivos acústicos, restaurarlos desde la copia externa y verificar cada SHA-256 con los inventarios CSV.

## Criterio de salida de la Fase 0

La fase queda cerrada porque existe un punto de retorno probado, el estado inicial está cuantificado, las anomalías están identificadas y las pruebas de referencia son satisfactorias. La siguiente fase puede diseñar `Site` y `Deployment` sin necesitar todavía acceso a la Raspberry Pi.
