import csv
import json
import os
import sqlite3
import time
from datetime import datetime, timezone

import requests

from node_config import (
    CSV_BACKUP,
    DURATION,
    NODE_NAME,
    OUTBOX_DB,
    OUTPUT_FOLDER_AUDIO,
    OUTPUT_FOLDER_IMG,
    RETENTION_DAYS,
    SAMPLE_RATE,
    SERVER_URL,
    getBackendAuthHeaders,
)
from deployment_context import (
    DeploymentConfigurationError,
    DeploymentContext,
    EventContext,
    deploymentContextFromLocationCommand,
    getCurrentDeploymentContext,
    getLegacyEventContext,
    persistCurrentDeploymentContext,
)


OUTBOX_LOCATION_MIGRATION = "20260823_01_location_context"


class RemoteLocationStateError(RuntimeError):
    """El servidor cambio de sitio, pero el nodo no pudo persistirlo."""


def obtenerOrdenCambioUbicacion():
    """Recoge, sin interrumpir la captura si no hay red, la orden pendiente."""
    try:
        response = requests.get(
            f"{SERVER_URL}/node/location-command",
            params={"device_name": NODE_NAME},
            headers=getBackendAuthHeaders(),
            timeout=20,
        )
        if response.status_code == 204:
            return None
        if response.status_code != 200:
            print(
                "No se pudo consultar el cambio de ubicacion: "
                f"HTTP {response.status_code}"
            )
            return None
        command = response.json()
        if not isinstance(command, dict):
            raise ValueError("respuesta JSON no valida")
        return command
    except (requests.exceptions.RequestException, ValueError) as exc:
        print(f"Cambio de ubicacion no disponible temporalmente: {exc}")
        return None


def confirmarOrdenCambioUbicacion(
    command_public_id,
    *,
    status,
    deployment_started_at=None,
    error_detail=None,
):
    payload = {
        "command_public_id": command_public_id,
        "status": status,
        "deployment_started_at": deployment_started_at,
        "error_detail": error_detail,
    }
    try:
        response = requests.post(
            f"{SERVER_URL}/node/location-command/ack",
            json=payload,
            headers=getBackendAuthHeaders(),
            timeout=20,
        )
        if response.status_code == 200:
            return True
        print(
            "No se pudo confirmar la orden de ubicacion: "
            f"HTTP {response.status_code}: {response.text[:300]}"
        )
    except requests.exceptions.RequestException as exc:
        print(f"ACK de ubicacion pendiente de reintento: {exc}")
    return False


def procesarCambioUbicacionPendiente() -> bool:
    """
    Activa y persiste una orden remota en un limite entre ciclos.

    Devuelve True cuando el proceso debe reiniciarse para reconstruir BirdNET
    con las nuevas coordenadas. Una indisponibilidad de red devuelve False y
    conserva el despliegue actual.
    """
    command = obtenerOrdenCambioUbicacion()
    if command is None:
        return False

    current = getCurrentDeploymentContext()
    same_deployment = (
        str(command.get("deployment_public_id"))
        == current.deployment_public_id
    )
    started_at = (
        current.started_at
        if same_deployment
        else datetime.now(timezone.utc).isoformat()
    )
    try:
        candidate = deploymentContextFromLocationCommand(
            command,
            started_at=started_at,
        )
    except DeploymentConfigurationError as exc:
        confirmarOrdenCambioUbicacion(
            command.get("public_id"),
            status="failed",
            error_detail=f"Orden invalida: {exc}",
        )
        return False

    try:
        activated = activarDespliegue(candidate, queue_on_failure=False)
    except RuntimeError as exc:
        confirmarOrdenCambioUbicacion(
            command.get("public_id"),
            status="failed",
            error_detail=f"Activacion rechazada: {exc}",
        )
        return False
    if not activated:
        return False

    try:
        if candidate != current:
            state_path = persistCurrentDeploymentContext(candidate)
            print(f"Nuevo despliegue guardado atomicamente en {state_path}")
    except Exception as exc:
        raise RemoteLocationStateError(
            "El backend activo el nuevo sitio, pero no se pudo guardar el "
            f"estado local: {exc}"
        ) from exc

    confirmed = confirmarOrdenCambioUbicacion(
        command.get("public_id"),
        status="applied",
        deployment_started_at=candidate.started_at,
    )
    if not confirmed:
        print(
            "El sitio ya esta aplicado localmente; el ACK se reintentara "
            "tras reiniciar."
        )
    return True


def _context_fields(context=None):
    if context is None:
        context = getCurrentDeploymentContext()
    if isinstance(context, (DeploymentContext, EventContext)):
        return context.event_fields()
    return {
        "device_name": context["device_name"],
        "site_code": context["site_code"],
        "deployment_public_id": context["deployment_public_id"],
    }


def subirArchivos(filename_base: str, context=None) -> bool:
    """Sube el WAV y el PNG asociados a `filename_base` al servidor."""
    url_archivos = f"{SERVER_URL}/upload/"
    ruta_audio = os.path.join(OUTPUT_FOLDER_AUDIO, f"{filename_base}.wav")
    ruta_img = os.path.join(OUTPUT_FOLDER_IMG, f"{filename_base}.png")
    archivos = {}
    archivos_abiertos = []

    try:
        if os.path.exists(ruta_audio):
            f_audio = open(ruta_audio, "rb")
            archivos["audio"] = (f"{filename_base}.wav", f_audio, "audio/wav")
            archivos_abiertos.append(f_audio)

        if os.path.exists(ruta_img):
            f_img = open(ruta_img, "rb")
            archivos["specto"] = (f"{filename_base}.png", f_img, "image/png")
            archivos_abiertos.append(f_img)

        if not archivos:
            print(" -> No hay archivos locales para subir.")
            return True

        r = requests.post(
            url_archivos,
            data=_context_fields(context),
            files=archivos,
            headers=getBackendAuthHeaders(),
            timeout=60,
        )
        if r.status_code == 200:
            print(" -> Archivos subidos correctamente.")
            return True

        print(f" -> Error subiendo archivos: {r.status_code}")
        return False

    except requests.exceptions.RequestException as e:
        print(f" -> Error de conexion subiendo archivos: {e}")
        return False
    finally:
        for f in archivos_abiertos:
            f.close()


def normalizarFilenameBase(filename):
    """Devuelve el nombre sin extension .wav."""
    return filename[:-4] if filename.endswith(".wav") else filename


def normalizarFilenameWav(filename):
    """Devuelve el nombre con extension .wav."""
    return filename if filename.endswith(".wav") else f"{filename}.wav"


def _outbox_now():
    return datetime.now().isoformat()


def inicializarOutboxOffline():
    """Crea la cola local transaccional usada cuando el backend no esta disponible."""
    with sqlite3.connect(OUTBOX_DB) as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_outbox_events_created
            ON outbox_events(created_at)
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )
        con.commit()


def guardarEventoOffline(event_type, payload, error=""):
    """
    Guarda un evento pendiente en SQLite.
    El payload se serializa ordenado para evitar duplicados exactos pendientes.
    """
    inicializarOutboxOffline()
    payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    ahora = _outbox_now()

    with sqlite3.connect(OUTBOX_DB) as con:
        existente = con.execute(
            """
            SELECT id FROM outbox_events
            WHERE event_type = ? AND payload = ?
            LIMIT 1
            """,
            (event_type, payload_json),
        ).fetchone()

        if existente:
            con.execute(
                """
                UPDATE outbox_events
                SET last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(error), ahora, existente[0]),
            )
            con.commit()
            print(f"Evento offline ya estaba pendiente: {event_type} #{existente[0]}")
            return existente[0]

        cur = con.execute(
            """
            INSERT INTO outbox_events(event_type, payload, last_error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_type, payload_json, str(error), ahora, ahora),
        )
        con.commit()
        event_id = cur.lastrowid

    print(f"Evento guardado en outbox offline: {event_type} #{event_id}")
    return event_id


def migrarCsvBackupLegacy(legacy_context=None):
    """Migra filas antiguas de backup_data.csv a la nueva cola SQLite."""
    if not os.path.isfile(CSV_BACKUP):
        return

    try:
        with open(CSV_BACKUP, mode="r", encoding="utf-8") as f:
            filas = list(csv.reader(f))

        if len(filas) <= 1:
            return

        if legacy_context is None:
            legacy_context = getLegacyEventContext()
        if legacy_context is None:
            raise RuntimeError(
                "backup_data.csv contiene eventos sin ubicacion y falta "
                "BIRDMONITOR_LEGACY_DEPLOYMENT_ID"
            )

        migradas = 0
        for fila in filas[1:]:
            try:
                ts, sp, conf, amp, fname = fila
                payload = {
                    "species": sp,
                    "confidence": float(conf),
                    "timestamp": ts,
                    "amplitude": float(amp),
                    "filename": normalizarFilenameBase(fname),
                }
                payload.update(_context_fields(legacy_context))
                guardarEventoOffline(
                    "detection",
                    payload,
                    "migrado desde backup_data.csv",
                )
                migradas += 1
            except Exception as e:
                print(f"No se pudo migrar fila legacy de backup: {e}")

        if migradas > 0:
            with open(CSV_BACKUP, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Species", "Confidence", "Amplitude", "Filename"])
            print(f"Migradas {migradas} filas legacy a {OUTBOX_DB}")

    except Exception as e:
        print(f"No se pudo migrar backup CSV legacy: {e}")
        raise


def migrarContextoOutboxLegacy(legacy_context=None):
    """Etiqueta eventos anteriores a la Fase 4 sin adoptar el sitio actual."""
    inicializarOutboxOffline()
    with sqlite3.connect(OUTBOX_DB) as con:
        rows = con.execute(
            """
            SELECT id, payload
            FROM outbox_events
            WHERE event_type != 'deployment_start'
            ORDER BY id
            """
        ).fetchall()
        pending = []
        for event_id, payload_json in rows:
            payload = json.loads(payload_json)
            if not all(
                payload.get(field)
                for field in (
                    "device_name",
                    "site_code",
                    "deployment_public_id",
                )
            ):
                pending.append((event_id, payload))

        if not pending:
            return 0
        if legacy_context is None:
            legacy_context = getLegacyEventContext()
        if legacy_context is None:
            raise RuntimeError(
                f"Hay {len(pending)} eventos offline sin ubicacion; "
                "configura BIRDMONITOR_LEGACY_DEPLOYMENT_ID antes de continuar"
            )

        legacy_fields = _context_fields(legacy_context)
        now = _outbox_now()
        for event_id, payload in pending:
            for key, value in legacy_fields.items():
                payload.setdefault(key, value)
            con.execute(
                """
                UPDATE outbox_events
                SET payload = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    now,
                    event_id,
                ),
            )
        con.execute(
            """
            INSERT INTO outbox_migrations(version, applied_at, details)
            VALUES (?, ?, ?)
            ON CONFLICT(version) DO UPDATE SET
                applied_at = excluded.applied_at,
                details = excluded.details
            """,
            (
                OUTBOX_LOCATION_MIGRATION,
                now,
                f"{len(pending)} eventos asociados a {legacy_fields['site_code']}",
            ),
        )
        con.commit()
    print(
        f"Contexto historico aplicado a {len(pending)} eventos offline: "
        f"{legacy_fields['site_code']}"
    )
    return len(pending)


def activarDespliegue(context=None, queue_on_failure=True):
    context = context or getCurrentDeploymentContext()
    payload = context.activation_payload()
    try:
        response = requests.post(
            f"{SERVER_URL}/node/deployments/activate",
            json=payload,
            headers=getBackendAuthHeaders(),
            timeout=30,
        )
        if response.status_code == 200:
            print(
                "Despliegue activo confirmado: "
                f"{context.site_code} ({context.deployment_public_id})"
            )
            return True
        error = f"HTTP {response.status_code}: {response.text[:300]}"
        if 400 <= response.status_code < 500:
            raise RuntimeError(
                "El backend rechazo la configuracion del despliegue: " + error
            )
    except requests.exceptions.RequestException as exc:
        error = str(exc)

    if queue_on_failure:
        guardarEventoOffline("deployment_start", payload, error)
        print("Activacion pendiente guardada en la cola offline.")
    else:
        print(f"No se pudo activar el despliegue: {error}")
    return False


def obtenerFilenameBasesPendientes():
    """Devuelve nombres base de WAV/PNG que siguen pendientes de sincronizacion."""
    inicializarOutboxOffline()
    pendientes = set()

    try:
        with sqlite3.connect(OUTBOX_DB) as con:
            filas = con.execute(
                """
                SELECT payload FROM outbox_events
                WHERE event_type IN ('detection', 'file_upload')
                """
            ).fetchall()

        for (payload_json,) in filas:
            try:
                payload = json.loads(payload_json)
                filename = payload.get("filename")
                if filename:
                    pendientes.add(normalizarFilenameBase(filename))
            except Exception:
                continue

    except Exception as e:
        print(f"No se pudieron consultar archivos pendientes: {e}")

    return pendientes


def enviarDatosServidor(
    species,
    confidence,
    filename,
    timestamp_str,
    amplitude,
    audio_start_seconds=None,
    audio_end_seconds=None,
):
    """Envia la deteccion al servidor FastAPI y sube los archivos asociados."""
    context = getCurrentDeploymentContext()
    datos = {
        "species": species,
        "confidence": confidence,
        "timestamp": timestamp_str,
        "filename": normalizarFilenameWav(filename),
        "amplitude": float(amplitude),
    }
    datos.update(context.event_fields())

    if audio_start_seconds is not None and audio_end_seconds is not None:
        datos["audio_start_seconds"] = float(audio_start_seconds)
        datos["audio_end_seconds"] = float(audio_end_seconds)

    try:
        r = requests.post(
            f"{SERVER_URL}/detections/",
            json=datos,
            headers=getBackendAuthHeaders(),
            timeout=60,
        )
        if r.status_code == 200:
            if subirArchivos(filename, context):
                sincronizarRespaldo()
            else:
                print(
                    "La deteccion llego al servidor, pero fallo la subida "
                    "de archivos. Guardando solo el upload para reintento..."
                )
                guardarEventoOffline(
                    "file_upload",
                    {
                        "filename": normalizarFilenameBase(filename),
                        **context.event_fields(),
                    },
                    "subida de archivos pendiente",
                )
        else:
            print(f"Servidor rechazo la deteccion ({r.status_code}). Guardando local...")
            guardarBackupLocal(
                species,
                confidence,
                timestamp_str,
                amplitude,
                normalizarFilenameBase(filename),
                audio_start_seconds,
                audio_end_seconds,
            )

    except requests.exceptions.RequestException as e:
        print(f"Error de conexion: {e}. Guardando local...")
        guardarBackupLocal(
            species,
            confidence,
            timestamp_str,
            amplitude,
            normalizarFilenameBase(filename),
            audio_start_seconds,
            audio_end_seconds,
        )


def enviarMetricasAcusticas(
    metricas,
    filename_wav,
    timestamp_str,
    rms_amplitude,
    calidad_audio=None,
    birdnet_info=None,
):
    """Envia al backend una fila de metricas acusticas por cada ciclo de grabacion."""
    metricas = metricas or {}
    calidad_audio = calidad_audio or {}
    birdnet_info = birdnet_info or {}

    context = getCurrentDeploymentContext()
    datos = {
        "timestamp": timestamp_str,
        "filename": normalizarFilenameWav(filename_wav),
        "sample_rate": SAMPLE_RATE,
        "duration": float(DURATION),
        "rms": float(rms_amplitude),
        "peak": float(calidad_audio.get("peak", 0.0)),
        "clipping_ratio": float(calidad_audio.get("clipping_ratio", 0.0)),
        "dc_offset": float(calidad_audio.get("dc_offset", 0.0)),
        "noise_floor_rms": float(calidad_audio.get("noise_floor_rms", 0.0)),
        "quality_status": calidad_audio.get("quality_status", "unknown"),
        "quality_detail": calidad_audio.get("quality_detail"),
        "mic_device": calidad_audio.get("mic_device"),
        "birdnet_model": birdnet_info.get("model_name"),
        "birdnet_model_version": birdnet_info.get("model_version"),
        "birdnetlib_version": birdnet_info.get("birdnetlib_version"),
        "acoustic_metrics_version": metricas.get(
            "acoustic_metrics_version", "legacy-v1"
        ),
        "aci": float(metricas.get("aci", 0.0)),
        "adi": float(metricas.get("adi", 0.0)),
        "aei": float(metricas.get("aei", 0.0)),
        "bio": float(metricas.get("bio", 0.0)),
        "ndsi": float(metricas.get("ndsi", 0.0)),
        "ht": float(metricas.get("ht", 0.0)),
        "hf": float(metricas.get("hf", 0.0)),
        "h": float(metricas.get("h", 0.0)),
    }
    datos.update(context.event_fields())

    try:
        r = requests.post(
            f"{SERVER_URL}/audio-metrics/",
            json=datos,
            headers=getBackendAuthHeaders(),
            timeout=60,
        )
        version_confirmada = True
        if datos["acoustic_metrics_version"] == "maad-v2":
            try:
                version_confirmada = (
                    r.json().get("acoustic_metrics_version") == "maad-v2"
                )
            except (AttributeError, TypeError, ValueError):
                version_confirmada = False

        if r.status_code == 200 and version_confirmada:
            print("Metricas acusticas enviadas al servidor.")
        else:
            detalle = getattr(r, "text", "")
            if r.status_code == 200:
                detalle = (
                    "backend sin soporte confirmado para "
                    "acoustic_metrics_version=maad-v2"
                )
            print(
                f"Servidor no confirmo las metricas acusticas "
                f"({r.status_code}): {detalle}"
            )
            guardarEventoOffline(
                "audio_metric",
                datos,
                f"HTTP {r.status_code}: {detalle}",
            )
    except requests.exceptions.RequestException as e:
        print(f"Error enviando metricas acusticas: {e}")
        guardarEventoOffline("audio_metric", datos, str(e))


def guardarBackupLocal(
    species,
    confidence,
    timestamp,
    amplitude,
    filename,
    audio_start_seconds=None,
    audio_end_seconds=None,
):
    """Guarda una deteccion en la cola local si el servidor no esta disponible."""
    payload = {
        "species": species,
        "confidence": float(confidence),
        "timestamp": timestamp,
        "amplitude": float(amplitude),
        "filename": normalizarFilenameBase(filename),
    }
    payload.update(getCurrentDeploymentContext().event_fields())

    if audio_start_seconds is not None and audio_end_seconds is not None:
        payload["audio_start_seconds"] = float(audio_start_seconds)
        payload["audio_end_seconds"] = float(audio_end_seconds)

    guardarEventoOffline(
        "detection",
        payload,
        "pendiente de sincronizacion",
    )


def limpiarArchivosAntiguos():
    """
    Mantiene la salud del sistema borrando archivos WAV y PNG antiguos.
    Con ciclos de 5 min se generan ~288 archivos/dia.
    """
    carpetas = [OUTPUT_FOLDER_AUDIO, OUTPUT_FOLDER_IMG]
    ahora = time.time()
    tiempo_vida = 86400 * RETENTION_DAYS
    pendientes = obtenerFilenameBasesPendientes()

    print(f"Iniciando limpieza de disco: conservando archivos de los ultimos {RETENTION_DAYS} dias...")
    archivos_borrados = 0

    for carpeta in carpetas:
        for archivo in os.listdir(carpeta):
            ruta_completa = os.path.join(carpeta, archivo)
            if os.path.isfile(ruta_completa):
                nombre_base = os.path.splitext(archivo)[0]
                if nombre_base in pendientes:
                    continue

                if os.stat(ruta_completa).st_mtime < (ahora - tiempo_vida):
                    try:
                        os.remove(ruta_completa)
                        archivos_borrados += 1
                    except Exception as e:
                        print(f"Error borrando {archivo}: {e}")

    if archivos_borrados > 0:
        print(f"Limpieza completada: {archivos_borrados} archivos eliminados.")


def sincronizarRespaldo():
    """
    Revisa eventos pendientes en la outbox local y, si hay conexion,
    los sube al servidor. Es seguro reintentar: el backend es idempotente.
    """
    inicializarOutboxOffline()

    try:
        with sqlite3.connect(OUTBOX_DB) as con:
            eventos = con.execute(
                """
                SELECT id, event_type, payload, attempts
                FROM outbox_events
                ORDER BY
                    CASE WHEN event_type = 'deployment_start' THEN 0 ELSE 1 END,
                    created_at ASC,
                    id ASC
                LIMIT 50
                """
            ).fetchall()

        if not eventos:
            return

        print(f"Intentando sincronizar {len(eventos)} eventos offline con el servidor...")
        enviados = 0

        for event_id, event_type, payload_json, attempts in eventos:
            try:
                payload = json.loads(payload_json)
                ok = False

                if event_type == "deployment_start":
                    response = requests.post(
                        f"{SERVER_URL}/node/deployments/activate",
                        json=payload,
                        headers=getBackendAuthHeaders(),
                        timeout=30,
                    )
                    ok = response.status_code == 200

                elif event_type == "detection":
                    filename_base = normalizarFilenameBase(payload["filename"])
                    datos_json = dict(payload)
                    datos_json["filename"] = normalizarFilenameWav(filename_base)
                    response = requests.post(
                        f"{SERVER_URL}/detections/",
                        json=datos_json,
                        headers=getBackendAuthHeaders(),
                        timeout=60,
                    )
                    ok = response.status_code == 200 and subirArchivos(
                        filename_base,
                        payload,
                    )

                elif event_type == "audio_metric":
                    response = requests.post(
                        f"{SERVER_URL}/audio-metrics/",
                        json=payload,
                        headers=getBackendAuthHeaders(),
                        timeout=60,
                    )
                    ok = response.status_code == 200
                    if (
                        ok
                        and payload.get("acoustic_metrics_version") == "maad-v2"
                    ):
                        try:
                            ok = (
                                response.json().get(
                                    "acoustic_metrics_version"
                                )
                                == "maad-v2"
                            )
                        except (AttributeError, TypeError, ValueError):
                            ok = False

                elif event_type == "file_upload":
                    ok = subirArchivos(
                        normalizarFilenameBase(payload["filename"]),
                        payload,
                    )

                else:
                    ok = False
                    print(
                        f"Evento offline desconocido conservado: "
                        f"{event_type} #{event_id}"
                    )

                with sqlite3.connect(OUTBOX_DB) as con:
                    if ok:
                        con.execute("DELETE FROM outbox_events WHERE id = ?", (event_id,))
                        enviados += 1
                        print(f" -> Evento offline sincronizado: {event_type} #{event_id}")
                    else:
                        con.execute(
                            """
                            UPDATE outbox_events
                            SET attempts = ?, last_error = ?, updated_at = ?
                            WHERE id = ?
                            """,
                            (attempts + 1, "Backend rechazo o no completo el evento", _outbox_now(), event_id),
                        )
                    con.commit()

            except Exception as e:
                print(f"Error sincronizando evento offline #{event_id}: {e}")
                with sqlite3.connect(OUTBOX_DB) as con:
                    con.execute(
                        """
                        UPDATE outbox_events
                        SET attempts = ?, last_error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (attempts + 1, str(e), _outbox_now(), event_id),
                    )
                    con.commit()

        if enviados > 0:
            print(f"Sincronizacion offline completada: {enviados} eventos enviados.")

    except Exception as e:
        print(f"Error general de sincronizacion: {e}")