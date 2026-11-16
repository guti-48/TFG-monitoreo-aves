# Escucha independiente (modo pull)

La Raspberry aloja el origen RTSP. Windows y Mac leen la misma fuente por
Tailscale y conservan sus propios MediaMTX, backend y sesiones web.
Ningun receptor consulta al otro ni manda una parada global al origen.

## Preparacion y activacion

1. Preparar las credenciales fuera de Git:

   `python scripts/independent_stream.py prepare --out stream-private --host IP_RASPBERRY --reader windows=IP_WINDOWS --reader mac=IP_MAC`

   Cada perfil JSON contiene una credencial privada. Entregar solo windows.json
   a Windows y mac.json al Mac. source.env y mediamtx-source.yml van a la Pi.
   El comando rechaza sobrescribir un directorio no vacio.

2. Instalar MediaMTX 1.19.2 ARM64 desde su publicacion oficial, verificando SHA256.
   En la Pi, desde el proyecto actualizado:

   `sudo bash scripts/raspberry_pi/install_independent_stream.sh /ruta/bundle pi /ruta/python /ruta/mediamtx`

   Instala birdstream-origin y birdstream-source, guarda copias y desactiva el
   publicador y supervisor anteriores. Si falla, intenta restaurar las unidades
   y su estado previo. Revisar la copia indicada si la recuperacion falla.
   El origen escucha solo en la IP privada elegida, exige credenciales y limita
   cada lector a su IP. No necesita un backend del portatil para autenticar.

3. En cada escritorio, desde el proyecto actualizado y su entorno Python:

   `python scripts/independent_stream.py configure-receiver --env backend/birdmonitor.env --profile /ruta/perfil.json`

   Conserva una copia birdmonitor.env.before-independent. El perfil debe quedar
   en una carpeta privada permanente y fuera de Git.
   En Windows ejecutar scripts/windows/apply_stream_security.ps1 como
   administrador. En macOS reiniciar el servicio con el instalador habitual
   scripts/macos/install_birdmonitor_macos.sh. Los dos recorridos renderizan el
   receptor al preparar MediaMTX. La web mantiene autenticacion y HLS local.

4. Actualizar tambien bounded_capture.py, audio_processing.py y main.py en la Pi
   y reiniciar birdmonitor.service para liberar el descriptor USB antiguo.
   La captura Linux con seleccion automatica usa arecord, con plazo de duracion
   mas 15 segundos. Tras un fallo se reabre el PCM en el siguiente ciclo.
   La seleccion numerica explicita BIRDMONITOR_MIC_DEVICE conserva el modo
   PortAudio anterior y no tiene esta recuperacion; dejarla vacia en la Pi.

## Comportamiento y limites

- Escuchar o desconectar solo cambia ese reproductor. La API rechaza con 409
  las antiguas ordenes globales cuando el servidor esta en modo pull.
- El estado inicial significa que hay una fuente configurada, no que ya se haya
  comprobado audio. La recepcion y reproduccion HLS determinan el estado real.
- Los sondeos de /stream/control no abren audio. MediaMTX de escritorio conecta
  bajo demanda; hlsAlwaysRemux esta desactivado. HLS puede mantener la conexion
  durante su periodo de cierre tras el ultimo cliente.
- La primera version mantiene una captura AAC continua en la Raspberry aunque
  no haya oyentes. Evita duplicar codificadores; consume CPU de forma continua.
- El publicador vigila timestamps: si no avanzan durante 20 segundos, termina;
  systemd vuelve a abrir el microfono tras 5 segundos. No imprime la URL secreta.
- La Raspberry y Tailscale deben estar disponibles. Apagar Windows no debe
  afectar al Mac ni viceversa. No se replican estados transitorios de directo.
- La aplicacion movil nativa conserva el protocolo anterior: esta entrega
  adapta el dashboard web, que tambien se puede abrir desde el movil.

## Validacion realizada el 13 de noviembre de 2026

La suite completa de 249 pruebas de Python paso. Se valido la sintaxis de JavaScript y PowerShell. MediaMTX 1.19.2
real recibio el microfono de la Raspberry en dos receptores aislados de Windows;
ambos devolvieron segmentos HLS de audio y el segundo continuo generando
segmentos nuevos tras detener el primero. La prueba se cerro sin sustituir
los servicios existentes. No equivale aun a una prueba fisica con el Mac,
ni a desenchufar el USB real: la recuperacion por timeout se probo simulada.
