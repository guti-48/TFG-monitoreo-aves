# Instalación en red local

Este modo es apropiado cuando el servidor, la Raspberry Pi y los navegadores
están en la misma red privada y confiable. No proporciona acceso desde
Internet.

## 1. Preparar el servidor

Desde la raíz del repositorio:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Coloca `mediamtx.exe` en:

```text
tools/mediamtx/mediamtx.exe
```

Se recomienda reservar en el router una IP para el servidor, por ejemplo
`192.168.1.10`, para que no cambie después de reiniciar.

## 2. Crear la cuenta y el token del nodo

```powershell
.\venv\Scripts\python.exe scripts\configure_security.py
```

El comando muestra una sola vez:

```text
BIRDMONITOR_NODE_API_TOKEN=...
```

Guárdalo temporalmente para el paso de la Raspberry. El servidor sólo conserva
su hash.

## 3. Elegir el modo local

```powershell
.\venv\Scripts\python.exe scripts\configure_network_mode.py `
  --mode local `
  --server-host 192.168.1.10
```

Sustituye el ejemplo por la IPv4 privada realmente asignada al servidor. El
configurador rechaza una IP pública, una IP Tailscale o una dirección que no
pertenezca al equipo.

## 4. Crear las credenciales de MediaMTX

```powershell
.\venv\Scripts\python.exe scripts\configure_stream_security.py
```

Conserva la contraseña de publicación mostrada. No la escribas en un archivo
del repositorio ni directamente en la unidad systemd.

## 5. Configurar la Raspberry

En `/etc/birdmonitor/birdmonitor.env` o en el archivo de entorno usado por
`birdmonitor.service`:

```bash
BIRDMONITOR_NETWORK_MODE=local
BIRDMONITOR_SERVER_URL=http://192.168.1.10:8000
BIRDMONITOR_NODE_API_TOKEN=TOKEN_MOSTRADO_POR_EL_SERVIDOR
BIRDMONITOR_DEPLOYMENT_STATE_FILE=/home/pi/birdmonitor/hardware/raspberry_pi/deployment_state.json
```

Si el nodo aún no está instalado, sigue primero la
[guía de Raspberry](../hardware/raspberry_pi/README.md): instala
`requirements-node.txt`, configura `micshared` y crea los tres servicios.
Después autoriza la publicación:

```bash
sudo python3 scripts/raspberry_pi/configure_stream_publisher.py \
  --network-mode local \
  --server-host 192.168.1.10
```

El programa solicita la contraseña sin mostrarla, corrige tanto la unidad
principal como sus posibles `drop-ins`, guarda la credencial en
`/etc/birdmonitor/stream-publisher.env` con permisos `600` y revierte el cambio
si FFmpeg entra en un bucle de reinicios.

Reinicia el nodo:

```bash
sudo systemctl restart birdmonitor.service
sudo systemctl status birdmonitor.service birdstream.service \
  birdmonitor-stream-supervisor.service --no-pager
```

Después de iniciar sesión en el dashboard se puede confirmar la ubicación
física del nodo. El cambio se recoge automáticamente en el siguiente límite
entre ciclos; no interrumpe una grabación en curso. No edites
`deployment_state.json`: es el estado atómico del despliegue y contiene
identificadores, no contraseñas.

## 6. Aplicar la seguridad en Windows

Abre PowerShell como administrador, entra en la raíz del repositorio y ejecuta:

```powershell
.\scripts\windows\apply_network_mode.ps1
```

El script:

- permite 8000 y 8554 sólo desde `LocalSubnet`;
- liga RTSP únicamente a la IP local elegida;
- mantiene HLS en `127.0.0.1:8888`;
- reconstruye las tareas sin ejecutar el backend como administrador;
- verifica autenticación, listeners y `/health`.

El lanzador espera hasta tres minutos a que Windows asigne la IP local elegida
antes de iniciar MediaMTX. Así evita un fallo por orden de arranque sin exponer
RTSP en interfaces adicionales.

## 7. Verificar

```powershell
.\scripts\windows\check_birdmonitor_windows.ps1
curl.exe http://127.0.0.1:8000/health
```

Desde otro dispositivo de la misma red:

```text
http://192.168.1.10:8000
```

Debe aparecer el inicio de sesión. Una red de invitados, otra VLAN o Internet
no deben alcanzar el servicio.

## Límites de este modo

El dashboard utiliza HTTP. Aunque haya autenticación, el tráfico no está
cifrado frente a otros participantes de la LAN. Este modo sólo debe usarse en
una red privada controlada. Para ubicaciones distintas, Wi-Fi compartida o
acceso remoto, usa el [modo Tailscale](INSTALACION_TAILSCALE.md).
