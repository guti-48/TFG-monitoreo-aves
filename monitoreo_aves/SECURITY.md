# Seguridad de BirdMonitor

## Despliegue admitido

BirdMonitor está diseñado para uso privado por una persona, familia, centro
educativo o pequeño equipo de investigación. Se admiten dos perfiles:

- LAN privada y confiable.
- Tailnet de Tailscale con dispositivos autorizados.

No se admite la publicación directa en Internet. No deben abrirse en el router
los puertos 8000, 8554 ni 8888. La app Flutter se considera legado; el cliente
soportado es el dashboard web.

## Controles implementados

- Cuenta administradora con contraseña almacenada mediante hash.
- Sesión firmada, cookie `HttpOnly`, `SameSite=Strict` y protección CSRF para
  cambios de estado.
- Token de nodo almacenado como hash y limitado a las operaciones de la
  Raspberry.
- Audios, espectrogramas, revisiones, analítica y exportaciones protegidos por
  sesión.
- Validación de rutas de archivos y del path HLS.
- MediaMTX con publicación, lectura RTSP y proxy HLS separados.
- HLS de MediaMTX sólo en loopback y entregado por FastAPI tras comprobar la
  sesión.
- RTSP ligado a la IP elegida y protegido por credenciales.
- Filtrado de origen y cabecera `Host` según el modo local o Tailscale.
- Reglas de Firewall de Windows limitadas a la subred local o al adaptador
  Tailscale.
- API, métricas, playback y protocolos de MediaMTX no utilizados desactivados.
- Secretos locales excluidos de Git y credencial de la Raspberry con permisos
  `600`.
- Backend y MediaMTX iniciados mediante tareas supervisadas y un envoltorio
  WScript sin consola; no dependen de una ventana abierta por el usuario.
- El lanzador de MediaMTX espera a que la IP del modo local o Tailscale esté
  asignada antes de enlazar RTSP. Se evita así una carrera al iniciar sesión
  sin ampliar la escucha a interfaces no autorizadas.
- El cambio remoto de ubicación sólo puede solicitarlo una sesión
  administradora con CSRF y confirmación física explícita. La Raspberry sólo
  puede recoger y confirmar la orden con su token limitado.
- Cada cambio de ubicación queda auditado, crea un UUID de campaña distinto y
  se aplica en el límite entre ciclos de grabación mediante estado local
  atómico. Un fallo de red conserva la ubicación anterior.

## Datos sensibles

Se consideran sensibles:

- contraseñas y tokens;
- cookies de sesión;
- audios y espectrogramas;
- ubicación exacta de los nodos;
- base de datos y exportaciones;
- registros que permitan inferir presencia o actividad en una vivienda.

No deben incluirse en commits, capturas públicas, memorias académicas,
incidencias ni copias compartidas. Los archivos reales de entorno se conservan
fuera de Git; sólo se versionan plantillas sin secretos.

## Modelo de confianza

Una Raspberry comprometida puede enviar datos falsos y conoce su propia
credencial de publicación, pero no recibe la contraseña administradora ni
permiso para descargar el archivo acústico. Un administrador local del servidor
o de la Raspberry puede acceder a los datos y secretos de ese equipo; el
proyecto no pretende protegerse frente al propietario con privilegios de
sistema.

Tailscale cifra el transporte y controla qué dispositivos forman parte de la
red privada. No elimina la necesidad de autenticación en BirdMonitor ni
autoriza por sí solo a todos los miembros de una tailnet.

## Limitaciones conocidas

- El modo LAN usa HTTP y sólo es adecuado para una red privada confiable. HTTPS
  sigue siendo recomendable para redes compartidas.
- RTSP presenta su credencial dentro de la URL utilizada por FFmpeg. El archivo
  está protegido, pero un administrador local de la Raspberry puede observar
  el proceso.
- El script de macOS no automatiza reglas avanzadas de su firewall.
- Faltan rate limiting global, cuotas de almacenamiento y una política de
  copias de seguridad cifradas.
- Se deben continuar las auditorías de XSS, fórmulas en exportaciones,
  validación profunda de subidas y dependencias.

## Operación segura

1. Instalar usando [`docs/INSTALACION.md`](docs/INSTALACION.md).
2. Usar contraseñas exclusivas y mantener Tailscale, Python, MediaMTX y el
   sistema operativo actualizados.
3. Revisar periódicamente `check_birdmonitor_windows.ps1`, los logs y el espacio
   disponible.
4. Realizar copias cifradas de la base de datos y de las evidencias necesarias.
5. No conservar audios más tiempo del necesario y documentar el consentimiento
   cuando el micrófono pueda captar voces.

## Respuesta ante un incidente

Si se sospecha una filtración:

1. Detener temporalmente `birdstream.service` y aislar el equipo afectado.
2. No borrar los logs antes de guardar una copia para el análisis.
3. Rotar cuenta/token con `scripts/configure_security.py`.
4. Rotar las identidades de streaming con
   `scripts/configure_stream_security.py --rotate` y volver a configurar la
   Raspberry.
5. Cerrar sesiones reiniciando el backend después de rotar el secreto de
   sesión.
6. Revisar dispositivos y políticas de acceso de Tailscale.
7. Comprobar que no se hayan versionado secretos y, si ocurrió, revocarlos:
   eliminarlos del último commit no basta.

## Comunicación de vulnerabilidades

Comunica el problema de forma privada al responsable del repositorio. Si está
habilitada la función **Report a vulnerability** de GitHub, utiliza un aviso de
seguridad privado. No abras una incidencia pública que contenga tokens,
contraseñas, direcciones privadas, audios o datos personales.

Incluye una descripción reproducible, versión o commit afectado, impacto y
medidas temporales conocidas, siempre sustituyendo los secretos por valores
ficticios.
