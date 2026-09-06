# Instalación segura de BirdMonitor

BirdMonitor admite dos formas de despliegue. La función del proyecto es la
misma en ambas: la Raspberry Pi analiza y envía los datos, mientras que el
servidor conserva la base de datos, sirve el dashboard y recibe el audio en
directo.

| Modo | Cuándo usarlo | Acceso permitido |
|---|---|---|
| [Red local](INSTALACION_LOCAL.md) | Raspberry, servidor y usuarios están en la misma red doméstica o de laboratorio | Únicamente la subred local |
| [Tailscale](INSTALACION_TAILSCALE.md) | La Raspberry o los usuarios se conectan desde ubicaciones distintas | Únicamente los dispositivos autorizados de la tailnet |

No se deben abrir los puertos 8000, 8554 ni 8888 en el router. El puerto 8888
es siempre interno y sólo escucha en `127.0.0.1`.

## Requisitos comunes

- Un servidor Windows 10/11 o macOS con Python 3.
- Una Raspberry Pi de 64 bits compatible con BirdNET, FFmpeg y ALSA. El
  repositorio incluye el instalador de sus tres servicios.
- El binario de MediaMTX colocado en la ruta indicada en el README.
- Una contraseña administradora exclusiva de al menos 12 caracteres.

## Orden de configuración

El orden es intencionado: primero se crean las identidades, después se elige la
red, luego se protege el streaming y sólo al final se exponen los servicios en
la interfaz seleccionada.

1. Clonar el repositorio e instalar `requirements.txt` en el servidor.
2. Ejecutar `scripts/configure_security.py`.
3. Guardar en la Raspberry el token mostrado una sola vez.
4. Ejecutar `scripts/configure_network_mode.py`.
5. Ejecutar `scripts/configure_stream_security.py`.
6. Instalar `requirements-node.txt`, ALSA compartido y los servicios de la
   Raspberry siguiendo su [guía](../hardware/raspberry_pi/README.md).
7. Configurar la credencial de publicación de `birdstream.service`.
8. Aplicar el perfil de red en el servidor y ejecutar las comprobaciones.

Los valores reales se guardan en `backend/birdmonitor.env` y en archivos de
`/etc/birdmonitor/`. Están excluidos de Git y nunca deben copiarse a la memoria
del TFG, capturas de pantalla, incidencias o commits.

## Cambio de un modo a otro

No es necesario reinstalar el proyecto ni perder datos. Se vuelve a ejecutar el
configurador con el nuevo modo y la nueva IP:

```powershell
.\venv\Scripts\python.exe scripts\configure_network_mode.py `
  --mode local|tailscale `
  --server-host IP_DEL_SERVIDOR
```

Después hay que repetir la configuración del publicador en la Raspberry y
aplicar el perfil del servidor. Las credenciales de aplicación y la base de
datos se conservan. Si se desea invalidar también la antigua credencial RTSP,
se puede rotar completamente con:

```powershell
.\venv\Scripts\python.exe scripts\configure_stream_security.py --rotate
```

La rotación obliga a volver a introducir la nueva contraseña de publicación en
la Raspberry.

Si sólo se ha expuesto la URL de lectura (por ejemplo, en una captura), conserva
la publicación de la Raspberry y rota únicamente el lector:

```powershell
.\venv\Scripts\python.exe scripts\configure_stream_security.py --rotate-reader
.\scripts\windows\repair_backend_task.ps1
```

## Comprobación común en Windows

```powershell
.\scripts\windows\check_birdmonitor_windows.ps1
```

El resultado correcto debe indicar:

- backend operativo y seguridad configurada;
- modo de red correcto;
- RTSP limitado a la IP seleccionada;
- HLS limitado a loopback;
- dos reglas de Firewall del grupo `BirdMonitor`;
- tareas `BirdMonitor Backend` y `BirdMonitor MediaMTX` en ejecución.
- backend y MediaMTX ejecutados mediante el envoltorio WScript sin consola; no
  debe quedar ninguna ventana de servicio abierta.

La descripción de las protecciones, limitaciones y respuesta ante incidentes se
encuentra en [`SECURITY.md`](../SECURITY.md). La evidencia técnica de su
implementación está en [`INFORME_SEGURIDAD.md`](INFORME_SEGURIDAD.md).
