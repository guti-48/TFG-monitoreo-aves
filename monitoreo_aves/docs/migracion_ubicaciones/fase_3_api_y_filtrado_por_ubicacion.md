# Fase 3 — API y aislamiento por ubicación

Fecha: 9 de agosto de 2026  
Estado: completada y validada en entorno aislado; pendiente de despliegue operativo  
Dependencias: Fases 1 y 2 completadas

## 1. Objetivo

Implementar el contrato de servidor necesario para que un mismo nodo físico pueda trabajar sucesivamente en Sevilla, Algeciras, Sangüesa u otros sitios sin mezclar observaciones, métricas, reglas aprendidas ni archivos acústicos.

La Raspberry Pi no ha intervenido en esta fase y puede permanecer desconectada. La base de datos operativa tampoco ha sido migrada: el backend que continúa en ejecución conserva el estado anterior y la nueva implementación se ha validado con bases temporales.

## 2. Resultado funcional

El backend ya es capaz de:

- crear, consultar, editar y archivar sitios sin borrar su histórico;
- activar de forma idempotente un despliegue y cerrar el anterior del mismo nodo;
- asociar cada detección y métrica al despliegue declarado por la Raspberry;
- rechazar asociaciones contradictorias entre sitio, despliegue y dispositivo;
- consultar detecciones, métricas, especies, analítica e informes por sitio o campaña;
- mantener las reglas aprendidas dentro del sitio en el que fueron generadas;
- almacenar los nuevos WAV y espectrogramas en directorios separados por sitio y despliegue;
- recuperar audios históricos desde su ruta plana anterior;
- servir el WAV de una detección mediante un endpoint autenticado basado en su identificador;
- aceptar temporalmente el formato antiguo mientras el nodo todavía no haya cambiado de ubicación.

## 3. Administración de sitios y despliegues

La funcionalidad está separada en [`features/locations`](../../backend/app/features/locations):

- [`routes.py`](../../backend/app/features/locations/routes.py) publica el contrato HTTP;
- [`service.py`](../../backend/app/features/locations/service.py) concentra las reglas de dominio y evita duplicar lógica en las rutas.

### 3.1 Endpoints administrativos

| Método y ruta | Función |
|---|---|
| `GET /sites/` | Lista sitios no archivados, sus campañas y totales. |
| `GET /sites/?include_archived=true` | Incluye sitios archivados. |
| `GET /sites/{site_id}` | Recupera un sitio y sus contadores. |
| `POST /sites/` | Crea un sitio validado. |
| `PATCH /sites/{site_id}` | Edita o archiva un sitio; su código no es modificable. |
| `GET /sites/{site_id}/deployments` | Devuelve todas las campañas de un sitio. |
| `GET /devices/{device_id}/deployments` | Devuelve el historial geográfico de un nodo. |

Las escrituras administrativas siguen protegidas por sesión y CSRF. Un sitio con un despliegue activo no se puede archivar.

### 3.2 Activación desde el nodo

La Raspberry utilizará:

```http
POST /node/deployments/activate
Authorization: Bearer <token-del-nodo>
Content-Type: application/json
```

Ejemplo sin credenciales reales:

```json
{
  "device_name": "birdmonitor",
  "deployment_public_id": "11111111-2222-4333-8444-555555555555",
  "site": {
    "code": "algeciras",
    "name": "Algeciras — instalación temporal",
    "municipality": "Algeciras",
    "region": "Cádiz",
    "country_code": "ES",
    "lat": 36.1408,
    "lon": -5.4562,
    "location_source": "manual",
    "location_accuracy_m": 10,
    "timezone": "Europe/Madrid"
  },
  "started_at": "2026-08-10T00:00:00Z",
  "notes": "Campaña temporal"
}
```

Reglas aplicadas:

1. el código del sitio identifica un lugar reutilizable;
2. el UUID identifica una campaña concreta y no es un secreto;
3. repetir el mismo UUID devuelve el mismo despliegue;
4. un UUID no se puede reutilizar con otro nodo o sitio;
5. activar una campaña nueva cierra la anterior en la misma transacción;
6. una activación antigua recibida con retraso no vuelve a cambiar la ubicación visible del dispositivo;
7. un nodo solo puede tener un despliegue activo.

El middleware de seguridad permite al token del nodo utilizar esta ruta, pero no le permite administrar sitios mediante las rutas del usuario.

## 4. Contrato de ingesta

`POST /detections/` y `POST /audio-metrics/` incorporan:

```json
{
  "device_name": "birdmonitor",
  "site_code": "algeciras",
  "deployment_public_id": "11111111-2222-4333-8444-555555555555"
}
```

El servidor resuelve el UUID a su identificador interno y verifica:

- que el despliegue existe;
- que pertenece al nodo indicado;
- que su sitio coincide con `site_code`;
- que la fecha del evento está comprendida en el periodo del despliegue;
- que un reintento no crea otra detección o métrica equivalente dentro de la misma campaña.

Las respuestas añaden:

- `deployment_id`: identificador interno para filtros administrativos;
- `deployment_public_id`: UUID estable utilizado por el nodo;
- `site_id`, `site_code` y `site_name`.

### 4.1 Compatibilidad temporal

Mientras la Raspberry no haya sido actualizada, los payloads sin sitio ni UUID se asignan al despliegue histórico legacy y generan una advertencia en el log.

Esta compatibilidad falla de forma segura cuando la fecha queda fuera del despliegue histórico. Por tanto, después de activar Algeciras, un cliente antiguo no puede enviar silenciosamente una observación nueva a Sevilla: recibe `409` y debe actualizarse para transmitir `deployment_public_id`.

No debe comenzarse una recogida real en una ubicación nueva antes de completar la Fase 4.

## 5. Consultas y separación científica

Se incorporaron filtros de servidor, no solo de interfaz, a los siguientes recursos:

| Recurso | Filtros principales |
|---|---|
| `GET /detections/` | `site_id`, `deployment_id`, `device_id`, `date_from`, `date_to` |
| `GET /audio-metrics/` | `site_id`, `deployment_id`, `device_id`, `date_from`, `date_to` |
| `GET /species/options` | `site_id`, `deployment_id` |
| `GET /analytics/biodiversity` | `site_id`, `deployment_id`, `device_id` |
| `GET /analytics/map` | `site_id`, `deployment_id`, `device_id` |
| `GET /analytics/daily-activity` | fecha, `site_id`, `deployment_id`, `device_id` |
| `GET /exports/report.xlsx` | fechas, `site_id`, `deployment_id`, `device_id` |
| `GET /learning/rules` | `site_id`, estado activo |

El filtro principal del dashboard será `site_id`. Si no se elige una campaña, el servidor agrega todos los despliegues históricos de ese sitio. Elegir `deployment_id` limita el resultado a una estancia concreta.

La analítica de biodiversidad agrupa por sitio y dispositivo. El mapa utiliza las coordenadas persistentes de `Site`, no la ubicación actual mutable del hardware, y rechaza combinaciones incompatibles entre sitio, campaña y nodo.

## 6. Aprendizaje local e invasoras

Las reglas generadas por revisión humana incluyen ahora `site_id`. La búsqueda de sugerencias exige que coincidan simultáneamente:

- dispositivo;
- sitio;
- especie original;
- intervalo acústico y de confianza previsto por la lógica existente.

Una aceptación aprendida para una especie introducida en Sevilla reaparecerá al volver a Sevilla, pero no se aplicará automáticamente en Algeciras. La reconstrucción completa del aprendizaje también recupera el sitio desde el despliegue de cada detección.

## 7. Archivos acústicos

Los uploads nuevos con contexto se guardan en rutas calculadas por el servidor:

```text
records/<site-code>/<deployment-uuid>/<filename>.wav
spectrograms/<site-code>/<deployment-uuid>/<filename>.png
```

El cliente no proporciona una ruta libre. El nombre continúa saneándose, se comprueba la extensión y se mantienen los límites de tamaño.

`POST /upload/` admite como campos multipart:

- `deployment_public_id`;
- `site_code`;
- `device_name`.

El UUID es el dato determinante. Si falta, el servidor solo aplica la compatibilidad por nombre cuando existe una única campaña posible. Si el mismo nombre aparece en varios despliegues, devuelve `409` en lugar de elegir uno arbitrariamente.

Los WAV históricos no se mueven. El resolvedor intenta primero la ruta segmentada y después la ruta plana antigua. La escucha y descarga de una detección se realiza mediante:

```text
GET /detections/{detection_id}/audio
```

Esta respuesta exige autenticación, utiliza `Cache-Control: private, no-store` y evita que el frontend tenga que construir una ruta física a partir del nombre del archivo.

## 8. Exportación Excel

El informe Excel mantiene su estructura visual, pero ahora puede limitarse por sitio o despliegue. Las hojas de detecciones y métricas incluyen el contexto geográfico y la biodiversidad se calcula por sitio, evitando sumar campañas incompatibles.

Si el usuario combina un `site_id` con un `deployment_id` que pertenece a otro sitio, la exportación se rechaza con `422` en vez de producir un informe engañoso.

Los enlaces de audio incluidos en el informe apuntan al endpoint protegido por identificador de detección.

## 9. Pruebas y criterios de aceptación

Se añadió [`test_locations_api.py`](../../tests/test_locations_api.py), que comprueba:

1. creación, edición, archivado e inmutabilidad del código del sitio;
2. activación idempotente y cierre de la campaña anterior;
3. reintentos retrasados sin regresión de la ubicación visible;
4. aislamiento de detecciones, métricas, analítica, mapa y Excel;
5. rechazo de asociaciones contradictorias;
6. aprendizaje restringido al sitio;
7. almacenamiento y descarga de WAV por despliegue;
8. rechazo de nombres de archivo ambiguos;
9. bloqueo de payloads legacy posteriores al cambio de ubicación;
10. permisos específicos del token del nodo.

Verificación final:

```text
Compilación Python: correcta
92 passed, 24 warnings in 8.70s
```

Las advertencias son las ya documentadas: ausencia de `ffmpeg` en el `PATH` del entorno de prueba y obsolescencia futura del adaptador temporal predeterminado de `sqlite3`. No hubo fallos.

## 10. Aislamiento de las pruebas y estado operativo

Durante esta fase se detectó y recuperó un incidente de aislamiento de `pytest`. Su trazabilidad completa está en [`incidente_aislamiento_pytest_fase_3.md`](incidente_aislamiento_pytest_fase_3.md).

Como medida permanente, [`conftest.py`](../../tests/conftest.py) fija una base aleatoria dentro de `.tmp` antes de que pytest recopile cualquier módulo. Por tanto, incluso un import prematuro del motor SQL no puede apuntar a `backend/app/birdmonitor.db`.

Comprobación final de la base operativa:

| Tabla | Filas |
|---|---:|
| `devices` | 1 |
| `detections` | 198 |
| `detection_reviews` | 174 |
| `audio_metrics` | 1 168 |
| `learning_examples` | 163 |
| `learning_rules` | 27 |

- coincidencia fila por fila con el respaldo congelado de la Fase 0: sí;
- `PRAGMA integrity_check`: `ok`;
- errores de claves foráneas: 0;
- `/health`: operativo y con seguridad requerida;
- migración operativa de sitios: todavía no aplicada.

## 11. Archivos principales modificados

- [`schemas.py`](../../backend/app/domain/schemas.py): contratos y validación;
- [`models.py`](../../backend/app/domain/models.py): relaciones de ubicación;
- [`migrations.py`](../../backend/app/core/migrations.py): identidad legacy compartida;
- [`locations`](../../backend/app/features/locations): administración y activación;
- [`detections/routes.py`](../../backend/app/features/detections/routes.py): ingesta, filtros y audio protegido;
- [`audio_metrics/routes.py`](../../backend/app/features/audio_metrics/routes.py): contexto y filtros;
- [`uploads/routes.py`](../../backend/app/features/uploads/routes.py): almacenamiento segmentado;
- [`learning/service.py`](../../backend/app/features/learning/service.py): aprendizaje local;
- [`exports/routes.py`](../../backend/app/features/exports/routes.py): informe por sitio o campaña;
- [`analisisBiodiversidad.py`](../../backend/analisisBiodiversidad.py): analítica con aislamiento geográfico;
- [`security.py`](../../backend/app/core/security.py): permiso mínimo para activar el despliegue.

## 12. Límite de la fase y siguiente paso

La API de ubicación está terminada, pero la Raspberry todavía envía el contrato anterior. La Fase 4 deberá:

1. incorporar sitio y UUID persistentes a la configuración local;
2. activar el despliegue antes de sincronizar eventos;
3. capturar una instantánea del contexto en cada elemento de la cola offline;
4. transmitir el contexto en detecciones, métricas y uploads;
5. actualizar las coordenadas utilizadas por BirdNET y BirdWeather;
6. etiquetar como Sevilla cualquier elemento legacy ya pendiente;
7. validar reintentos, cortes de red y reinicios sin regenerar el UUID.

Hasta entonces, no se modifica la Raspberry ni se inicia la campaña de Algeciras con el backend nuevo.
