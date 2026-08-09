# Registro de incidente — aislamiento de pytest en la Fase 3

Fecha: 9 de agosto de 2026  
Estado: recuperado, verificado y prevenido  
Impacto final: sin pérdida lógica respecto al estado operativo congelado al comenzar las fases

## 1. Resumen

Una prueba nueva importó dos módulos del backend durante la recopilación de pytest, antes de que el fixture de sesión configurase `BIRDMONITOR_DB_PATH`. Como consecuencia, el motor SQL se inicializó contra la ruta operativa predeterminada y el fixture de pruebas ejecutó su reinicialización sobre ese archivo.

El problema se detectó en la primera ejecución afectada al observar conteos incompatibles con la auditoría de la Fase 0. Se detuvieron las pruebas, se preservó el estado contaminado y se restauró la copia verificada antes de continuar.

## 2. Causa raíz

Los imports prematuros eran:

```python
from backend.app.features.detections import media as review_media
from backend.app.features.uploads import routes as upload_routes
```

El segundo alcanzaba `backend.app.core.database` durante la recopilación. En ese momento el fixture `test_db_path` todavía no se había ejecutado, por lo que cambiar la variable de entorno posteriormente no podía modificar el motor ya creado.

El defecto no estaba en SQLite ni en la migración: estaba en el orden de inicialización del entorno de pruebas.

## 3. Evidencia detectada

El estado contaminado contenía datos sintéticos de los tests:

| Tabla | Filas |
|---|---:|
| `devices` | 14 |
| `detections` | 15 |
| `detection_reviews` | 4 |
| `audio_metrics` | 3 |
| `learning_examples` | 4 |
| `learning_rules` | 2 |
| `sites` | 15 |
| `deployments` | 15 |

La diferencia frente a los conteos congelados permitió identificar el incidente inmediatamente.

## 4. Preservación y recuperación

Antes de restaurar se creó una copia consistente mediante la API de copia en línea de SQLite:

```text
backend/app/backups/phase3-test-isolation-incident-20260809-202710/
└── birdmonitor.test-contaminated.db
```

Datos del artefacto:

- tamaño: 741 376 bytes;
- SHA-256: `28D429CEE90B5B0DE064A9488A2C929A273A5E5E8F2EAEA40C31AF5985DB2B2C`;
- `PRAGMA integrity_check`: `ok`.

Después se restauró mediante la misma API el respaldo verificado:

```text
backend/app/backups/phase0-location-20260809-193418/birdmonitor.db
```

SHA-256 del origen: `3F91537B8C053BBCCD87C72BE6B06F09B47D406BD660D77C8BC96A4694CAB60F`.

La copia en línea puede producir una organización física distinta de las páginas y, por ello, un hash físico diferente en el archivo destino. La validación adecuada se realizó comparando todas las filas y columnas de cada tabla con el origen.

Resultado:

| Comprobación | Resultado |
|---|---|
| Seis tablas originales | coincidencia exacta fila por fila |
| Detecciones | 198 |
| Revisiones | 174 |
| Métricas | 1 168 |
| Ejemplos de aprendizaje | 163 |
| Reglas de aprendizaje | 27 |
| Dispositivos | 1 |
| Integridad SQLite | `ok` |
| Errores de clave foránea | 0 |
| Respuesta `/health` | correcta |

El estado restaurado coincide con el que estaba documentado al inicio de la migración, cuando la Raspberry ya se encontraba desconectada.

## 5. Corrección permanente

[`tests/conftest.py`](../../tests/conftest.py) ahora realiza el aislamiento durante su propia importación, antes de que pytest recopile módulos de prueba:

1. genera una ruta aleatoria bajo `.tmp`;
2. establece inmediatamente `BIRDMONITOR_DB_PATH`;
3. después permite importar cualquier módulo del backend;
4. todos los fixtures reutilizan esa misma ruta aislada.

Además, los imports concretos que originaron el problema se trasladaron al cuerpo de la prueba que los necesita.

Esta defensa doble evita depender del orden de los tests. Tras aplicarla se ejecutaron las pruebas de ubicación y la suite completa, y se comparó nuevamente la base operativa contra el respaldo:

```text
6 pruebas de ubicación superadas
92 pruebas totales superadas
base operativa idéntica fila por fila al estado de la Fase 0
```

## 6. Lección operativa

Un fixture que cambia una variable de entorno no protege frente a imports realizados durante la recopilación si el recurso dependiente ya se inicializó. Las rutas de recursos destructivos de prueba deben fijarse antes de importar la aplicación y deben ser distintas por ejecución.

El artefacto contaminado se conserva para auditoría. No debe utilizarse como respaldo operativo ni incorporarse a análisis científicos.
