# Instalación con Tailscale

Este es el modo recomendado cuando el servidor, la Raspberry o los usuarios
pueden estar en redes diferentes. Tailscale crea una red privada cifrada entre
los dispositivos sin abrir puertos del router.

Tailscale no sustituye la seguridad de BirdMonitor: el dashboard sigue
exigiendo sesión, la Raspberry usa un token limitado y RTSP mantiene
credenciales independientes.

## 1. Preparar la tailnet

Instala Tailscale e inicia sesión en:

- el servidor central;
- la Raspberry Pi;
- cada ordenador o móvil que deba abrir el dashboard.

Comprueba la conectividad:

```powershell
tailscale status
tailscale ip -4
```

En la Raspberry:

```bash
sudo systemctl is-active tailscaled.service
tailscale ping IP_TAILSCALE_SERVIDOR
```

No configures reenvío de puertos, DMZ ni reglas de entrada en el router. En una
tailnet con varios usuarios, limita mediante las políticas de acceso de
Tailscale qué dispositivos pueden llegar al servidor y a los puertos 8000 y
8554.

## 2. Preparar BirdMonitor en el servidor

Desde la raíz del repositorio:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\venv\Scripts\python.exe scripts\configure_security.py
```

Guarda el `BIRDMONITOR_NODE_API_TOKEN` mostrado una sola vez. Coloca también
`mediamtx.exe` en `tools/mediamtx/mediamtx.exe`.

## 3. Elegir el modo Tailscale

Puedes omitir `--server-host` para que se detecte con `tailscale ip -4`, o
indicarlo explícitamente:

```powershell
.\venv\Scripts\python.exe scripts\configure_network_mode.py `
  --mode tailscale `
  --server-host 100.x.y.z
```

Usa la IP Tailscale del servidor, no la de la Raspberry ni la Wi-Fi. El
configurador comprueba que pertenezca al rango Tailscale y esté asignada al
equipo.

## 4. Proteger MediaMTX

```powershell
.\venv\Scripts\python.exe scripts\configure_stream_security.py
```

Guarda la contraseña de publicación mostrada para introducirla en la Raspberry.

## 5. Configurar la Raspberry

En `/etc/birdmonitor/birdmonitor.env`:

```bash
BIRDMONITOR_NETWORK_MODE=tailscale
BIRDMONITOR_SERVER_URL=http://100.x.y.z:8000
BIRDMONITOR_NODE_API_TOKEN=TOKEN_MOSTRADO_POR_EL_SERVIDOR
BIRDMONITOR_DEPLOYMENT_STATE_FILE=/home/pi/birdmonitor/hardware/raspberry_pi/deployment_state.json
```

Si el nodo aún no está instalado, sigue primero la
[guía de Raspberry](../hardware/raspberry_pi/README.md): instala
`requirements-node.txt`, configura `micshared` y crea los tres servicios.
Después autoriza la publicación:

```bash
sudo python3 scripts/raspberry_pi/configure_stream_publisher.py \
  --network-mode tailscale \
  --server-host 100.x.y.z
```

El instalador se niega a continuar si `tailscaled.service` no está activo. La
contraseña queda en `/etc/birdmonitor/stream-publisher.env`, con permisos
`600`, y no en Git ni en el historial del shell.

```bash
sudo systemctl restart birdmonitor.service
sudo systemctl status tailscaled.service birdmonitor.service \
  birdstream.service birdmonitor-stream-supervisor.service --no-pager
```

Después de iniciar sesión, el dashboard solicita confirmar dónde está
físicamente la Raspberry. Una orden remota se aplica automáticamente entre
ciclos y reinicia sólo `birdmonitor.service` para recargar BirdNET con las
nuevas coordenadas; el streaming independiente continúa supervisado.

## 6. Aplicar la seguridad en Windows

Abre PowerShell como administrador:

```powershell
Set-Location "RUTA\AL\REPOSITORIO\TFG-monitoreo-aves"
.\scripts\windows\apply_network_mode.ps1
```

El script limita el Firewall al adaptador Tailscale y al rango IPv4 de la
tailnet, liga RTSP a la IP Tailscale exacta y conserva HLS sólo en loopback.
En los inicios de sesión posteriores, MediaMTX espera hasta tres minutos a que
Tailscale asigne esa IP antes de arrancar. No cambia a una interfaz más amplia
si la red privada tarda en estar disponible.

## 7. Verificar

```powershell
.\scripts\windows\check_birdmonitor_windows.ps1
curl.exe http://127.0.0.1:8000/health
curl.exe http://100.x.y.z:8000/health
```

Desde un dispositivo autorizado y conectado a Tailscale:

```text
http://100.x.y.z:8000
```

Desde un dispositivo sin Tailscale, la IP LAN del servidor o Internet no debe
estar disponible en este modo.

## macOS

Después de configurar las variables se puede usar:

```bash
./scripts/macos/install_birdmonitor_macos.sh
./scripts/macos/check_birdmonitor_macos.sh
```

El arranque liga RTSP a la IP Tailscale elegida y HLS a loopback. La
automatización actual no modifica el firewall de macOS; la restricción de
origen del backend y el enlace a la interfaz concreta siguen activos, pero el
administrador debe revisar el firewall del sistema.

## Referencias de Tailscale

- [Direcciones IP de Tailscale](https://tailscale.com/docs/concepts/tailscale-ip-addresses)
- [Conectar dispositivos](https://tailscale.com/docs/how-to/connect-to-devices)
- [Políticas de acceso](https://tailscale.com/docs/features/access-control)
