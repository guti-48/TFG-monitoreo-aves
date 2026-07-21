import time
import numpy as np
import requests
from datetime import datetime
from audio_processing import (
    calcularMetricasAcusticas,
    generacionEspectograma,
    grabacionAudio,
    guardoWAV,
    listarDispositivosAudio,
    resolverDispositivoEntrada,
)
from analyzer import BirdAnalyzer
from node_config import (
    DURATION,
    INTERVALO,
    NODE_NAME,
    SAMPLE_RATE,
    SERVER_URL,
    UMBRAL_AVES,
    UMBRAL_HUMANOS,
    UMBRAL_MOTORES,
    UMBRAL_RUIDO_ALTO,
)
from birdweather_client import enviarDatosBirdWeather
from node_location import obtenerUbicacionNodo
from node_sync import (
    enviarDatosServidor,
    enviarMetricasAcusticas,
    inicializarOutboxOffline,
    limpiarArchivosAntiguos,
    migrarCsvBackupLegacy,
    sincronizarRespaldo,
)

# Se carga una única vez el modelo
def get_brain():
    return BirdAnalyzer()

def esperarSiguienteCiclo(inicio_ciclo):
    """Espera hasta completar el intervalo configurado del ciclo."""
    tiempo_usado = time.time() - inicio_ciclo
    tiempo_espera = INTERVALO - tiempo_usado

    if tiempo_espera > 0:
        print(
            f"Ciclo completado en {tiempo_usado:.1f}s. "
            f"Esperando {tiempo_espera:.1f}s hasta el siguiente ciclo...\n"
        )
        time.sleep(tiempo_espera)
    else:
        print(
            f"Aviso: el ciclo tardó {tiempo_usado:.1f}s (>{INTERVALO}s). "
            f"Arrancando siguiente ciclo sin espera.\n"
        )

### Flujo de trabajo principal ###
if __name__ == "__main__":

    brain = get_brain()
    listarDispositivosAudio()
    device_index = resolverDispositivoEntrada()
    ubicacion_nodo = obtenerUbicacionNodo()
    print("Verificando reloj interno")
    while datetime.now().year < 2024:
        print("Esperando a que el sistema sincronice la hora por WiFi...")
        time.sleep(5)
    print("Hora correcta sincronizada. Arrancando nodo.")
    print(f"Ciclo configurado: {DURATION}s de grabación cada {INTERVALO}s ({INTERVALO//60} min).")
    inicializarOutboxOffline()
    migrarCsvBackupLegacy()

    try:
        # Registro inicial del dispositivo
        try:
            requests.post(
                f"{SERVER_URL}/devices/",
                json={
                    "name": NODE_NAME,
                    "location": ubicacion_nodo["location"],
                    "lat": ubicacion_nodo.get("lat"),
                    "lon": ubicacion_nodo.get("lon"),
                },
                timeout=10,
            )
        except:
            print("No se pudo registrar el dispositivo en el servidor.")

        while True:
            #Marcamos el inicio del ciclo
            inicio_ciclo = time.time()

            try:
                sincronizarRespaldo()

                now         = datetime.now()
                timestampDB = now.isoformat()
                timestamp   = now.strftime("%Y-%m-%d_%H-%M-%S")
                filename    = f"record_{timestamp}"
                filenameWAV = f"{filename}.wav"

                # Grabación (60 segundos)
                if device_index is None:
                    print("Modo centinela: no hay micrófono disponible, se reintentara en el siguiente ciclo.")
                    device_index = resolverDispositivoEntrada()
                    continue

                audio_data = grabacionAudio(DURATION, SAMPLE_RATE, device_index)
                rms_amplitude = float(np.sqrt(np.mean(audio_data ** 2)))
                print(f"Nivel de Audio (RMS): {rms_amplitude:.4f}")

                #Guardar WAV y espectrograma
                audio_path = guardoWAV(audio_data, SAMPLE_RATE, filenameWAV)
                generacionEspectograma(audio_path, filename)
                print("Proceso completado, revisa las carpetas de salida.")

                # Métricas acústicas del ciclo completo.
                # Se envían siempre que se puedan calcular, aunque no haya aves detectadas.
                metricas_acusticas = calcularMetricasAcusticas(audio_path)
                enviarMetricasAcusticas(metricas_acusticas, filenameWAV, timestampDB, rms_amplitude)

                #Análisis BirdNET
                print("Analizando especies de aves y ruidos...")
                res = brain.predict(audio_path)

                detecciones_unicas = {}

                if res:
                    for r in res:
                        especie   = r['species']
                        confianza = r['confidence']

                        es_humano = "Human" in especie
                        es_motor  = "Motor" in especie or "Noise" in especie
                        es_ruido  = es_humano or es_motor

                        if es_humano and confianza >= UMBRAL_HUMANOS:
                            if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                                detecciones_unicas[especie] = r

                        elif es_motor and confianza >= UMBRAL_MOTORES:
                            if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                                detecciones_unicas[especie] = r

                        elif not es_ruido and confianza >= UMBRAL_AVES:
                            if especie not in detecciones_unicas or confianza > detecciones_unicas[especie]['confidence']:
                                detecciones_unicas[especie] = r

                    if detecciones_unicas:
                        print(f"Captadas {len(detecciones_unicas)} fuentes sonoras.")
                    elif rms_amplitude > UMBRAL_RUIDO_ALTO:
                        print("Mucho ruido, sin clasificación clara. Marcando como Ruido Ambiente.")
                        detecciones_unicas['Noise_Ambiente'] = {
                            'species':    'Noise_Ruido Ambiente',
                            'confidence': 1.0
                        }
                else:
                    if rms_amplitude > UMBRAL_RUIDO_ALTO:
                        print("Ruido alto detectado. Marcando como Ruido Ambiente.")
                        detecciones_unicas['Noise_Ambiente'] = {
                            'species':    'Noise_Ruido Ambiente',
                            'confidence': 1.0
                        }

                # Enviar resultados
                if detecciones_unicas:
                    print("Enviando datos...")
                    for especie, datos in detecciones_unicas.items():
                        print(f" -> {especie} ({datos['confidence']*100:.1f}%) [Vol: {rms_amplitude:.3f}]")

                        enviarDatosServidor(
                            species=datos['species'],
                            confidence=datos['confidence'],
                            filename=filename,          
                            timestamp_str=timestampDB,
                            amplitude=rms_amplitude,
                        )

                        nombre_especie = datos['species']
                        if "Human" not in nombre_especie and "Motor" not in nombre_especie and "Noise" not in nombre_especie:
                            enviarDatosBirdWeather(
                                species=nombre_especie,
                                confidence=datos['confidence'],
                                timestamp=timestampDB,
                                lat=ubicacion_nodo["lat"] if ubicacion_nodo["lat"] is not None else brain.lat,
                                lon=ubicacion_nodo["lon"] if ubicacion_nodo["lon"] is not None else brain.lon,
                            )
                else:
                    print("Silencio o ruido bajo irrelevante. No se guarda nada.")

                limpiarArchivosAntiguos()
            
            except Exception as e:
                print(f"Error controlado en el ciclo principal (el nodo continuara en el siguiente ciclo): {e}")
                device_index = resolverDispositivoEntrada()
            finally:
                esperarSiguienteCiclo(inicio_ciclo)

    except KeyboardInterrupt:
        print("\nPrograma interrumpido.")
    except Exception as e:
        print(f"\nOcurrió un error: {e}")
