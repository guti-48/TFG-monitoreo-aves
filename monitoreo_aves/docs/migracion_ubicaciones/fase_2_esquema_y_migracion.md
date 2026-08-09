# Fase 2 — esquema y migración histórica

Fecha: 9 de agosto de 2026  
Estado: completada y validada sobre copias; pendiente de despliegue operativo  
Migración: `20260809_01_sites_deployments`

## 1. Objetivo

Incorporar el modelo `Site`/`Deployment` definido en la Fase 1 y preparar una migración automática, transaccional e idempotente que asigne toda la información histórica existente al sitio de Sevilla sin modificar sus valores científicos originales.

La base de datos operativa no se ha migrado durante esta fase. La Raspberry Pi permaneció desconectada y no fue necesaria.

## 2. Implementación

### 2.1 Modelo de dominio

Se añadieron tres entidades en [`models.py`](../../backend/app/domain/models.py):

- `SchemaMigration`: historial de versiones aplicadas;
- `Site`: lugar geográfico estable;
- `Deployment`: periodo de instalación de un dispositivo en un sitio.

También se añadieron las relaciones:

- `Detection.deployment_id`;
- `AudioMetric.deployment_id`;
- `LearningRule.site_id`;
- `Device.deployments`;
- relaciones inversas desde sitio y despliegue.

El esquema incorpora restricciones para:

- código de sitio único;
- coordenadas completas y dentro de rango;
- precisión geográfica no negativa;
- UUID de despliegue único;
- fecha final igual o posterior a la inicial;
- un único despliegue activo por dispositivo mediante índice único parcial.

Los nuevos campos de relación son temporalmente anulables para permitir que el backend se actualice antes que la Raspberry Pi. La migración exige, sin embargo, que ninguna fila histórica quede a `NULL`. La Fase 3 hará que toda inserción nueva resuelva obligatoriamente su despliegue antes de almacenarse.

### 2.2 Motor SQLite

[`database.py`](../../backend/app/core/database.py) configura cada conexión con:

```sql
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
```

La primera directiva hace que SQLite aplique realmente las claves foráneas declaradas. La segunda evita fallos inmediatos ante escrituras concurrentes breves sin ocultar bloqueos persistentes.

### 2.3 Migración versionada

La lógica se encuentra en [`migrations.py`](../../backend/app/core/migrations.py). `main.py` conserva la función pública `asegurar_esquema_runtime()`, pero ahora delega en un único procedimiento versionado.

Secuencia de ejecución:

1. crear las tablas nuevas si todavía no existen;
2. conservar las ampliaciones de esquema anteriores;
3. consultar `schema_migrations`;
4. añadir las columnas de relación si faltan;
5. crear los índices de consulta;
6. crear o reutilizar el sitio `sevilla`;
7. crear un despliegue histórico determinista por dispositivo;
8. asignar detecciones y métricas a su despliegue;
9. limitar las reglas aprendidas al sitio histórico;
10. comprobar filas huérfanas y cruces entre dispositivos;
11. proteger los eventos posteriores contra nuevos duplicados;
12. registrar la versión únicamente después de superar todas las comprobaciones.

Si una comprobación falla, la transacción no registra la migración como completada. Repetir el procedimiento después de corregir la causa es seguro.

## 3. Identidad histórica

La configuración predeterminada utilizada para esta instalación es:

| Propiedad | Valor |
|---|---|
| Código | `sevilla` |
| Nombre | nombre geográfico actual del dispositivo |
| País | `ES` |
| Zona horaria | `Europe/Madrid` |
| Coordenadas | coordenadas históricas del dispositivo |
| Origen | origen histórico de esas coordenadas |

El UUID del despliegue histórico se genera con UUID v5 a partir del código del sitio y el identificador del dispositivo. Por ello, el mismo intento de migración produce la misma identidad y no duplica campañas.

Los valores pueden parametrizarse antes de un despliegue distinto mediante:

- `BIRDMONITOR_LEGACY_SITE_CODE`;
- `BIRDMONITOR_LEGACY_SITE_NAME`;
- `BIRDMONITOR_LEGACY_MUNICIPALITY`;
- `BIRDMONITOR_LEGACY_REGION`;
- `BIRDMONITOR_LEGACY_COUNTRY_CODE`;
- `BIRDMONITOR_LEGACY_TIMEZONE`.

El código y el país se validan antes de escribir cualquier dato.

## 4. Conservación de duplicados históricos

La auditoría de la Fase 0 identificó cuatro grupos duplicados en detecciones y un grupo en métricas. Se han conservado deliberadamente: eliminarlos dentro de una migración estructural alteraría el conjunto científico sin una decisión separada.

Para impedir que esta compatibilidad permita nuevos duplicados, la migración crea índices únicos parciales aplicables a los identificadores posteriores al último registro histórico:

- `uq_detections_deployment_event_post_location_migration`;
- `uq_audio_metric_deployment_event_post_location_migration`.

Así se preserva íntegramente la evidencia antigua y se protegen los eventos nuevos. La API continuará aplicando además su comprobación idempotente.

## 5. Ensayo sobre una base sintética

Se añadieron cinco pruebas en [`test_location_migration.py`](../../tests/test_location_migration.py):

1. migración a Sevilla sin perder duplicados;
2. segunda ejecución sin cambios ni nuevas entidades;
3. rechazo de dos despliegues activos simultáneos;
4. validación de pareja y rango de coordenadas;
5. conservación de duplicados legacy y rechazo de duplicados nuevos.

Resultado específico:

```text
5 passed
```

## 6. Ensayo sobre la copia real de la Fase 0

Se copió el respaldo a `.tmp/phase2_real_backup_migration_final.db` y la migración se ejecutó exclusivamente sobre esa copia.

### 6.1 Integridad

| Comprobación | Resultado |
|---|---|
| Primera ejecución | aplicada |
| Segunda ejecución | sin cambios |
| `PRAGMA integrity_check` | `ok` |
| Errores de clave foránea | 0 |
| Campos originales | hash lógico idéntico antes y después |
| Sitios | 1 (`sevilla`) |
| Despliegues | 1 |

### 6.2 Asignación

| Colección | Total | Sin contexto tras migrar |
|---|---:|---:|
| Detecciones | 198 | 0 |
| Métricas acústicas | 1 168 | 0 |
| Reglas de aprendizaje | 27 | 0 |

Se mantuvieron además las 174 revisiones y los 163 ejemplos de aprendizaje, ya que sus claves y valores originales no se modificaron.

### 6.3 Hashes físicos

- respaldo original: `3F91537B8C053BBCCD87C72BE6B06F09B47D406BD660D77C8BC96A4694CAB60F`;
- copia temporal migrada: `5D765EC121560AE2688C077471DAA7DF468CB88A2239B6E20D258FC81090BC73`.

El cambio de hash de la copia es el esperado al añadir tablas, columnas, índices y asociaciones. El respaldo original conservó exactamente el hash registrado en la Fase 0.

## 7. Regresión del proyecto

Se compiló el paquete y se ejecutó toda la suite:

```text
85 passed, 24 warnings in 8.07s
```

No hubo errores. Las advertencias corresponden a:

- `pydub`, que no localiza `ffmpeg/avconv` en el `PATH` del entorno de pruebas;
- el adaptador de fechas de `sqlite3` que Python 3.12 marca como obsoleto para una versión futura.

Ninguna afecta a la migración ni altera los resultados. La segunda se tratará separadamente cuando se actualice la estrategia global de serialización temporal, evitando mezclarla con esta fase.

## 8. Recuperación

El código todavía no se ha aplicado a la base operativa. Cuando llegue la fase de despliegue:

1. se verificará otra vez el respaldo de la Fase 0;
2. se detendrá el backend;
3. se creará una copia inmediatamente anterior al despliegue;
4. se iniciará el backend para ejecutar la migración;
5. se repetirán conteos, integridad y claves foráneas;
6. si falla cualquier criterio, se detendrá el backend y se restaurará la copia anterior.

No será necesario recuperar nada mientras el despliegue no se haya realizado.

## 9. Resultado y límite de la fase

El esquema y la migración histórica están implementados, automatizados y validados. La fase no añade todavía endpoints para crear Algeciras ni permite que los payloads del nodo seleccionen una campaña: esa funcionalidad corresponde a la Fase 3.

Hasta completar la Fase 3 y actualizar la Raspberry Pi, no debe iniciarse una recogida real en Algeciras con el backend migrado, porque los clientes antiguos aún no transmiten el identificador geográfico de cada evento.
