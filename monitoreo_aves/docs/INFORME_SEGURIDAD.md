# Informe técnico de seguridad de BirdMonitor

Fecha de revisión: 23 de agosto de 2026  
Estado: controles principales implementados y verificados

## 1. Alcance y criterio de despliegue

BirdMonitor está pensado para una instalación privada autogestionada. Cada persona despliega su propio backend, base de datos y Raspberry Pi. El repositorio no contiene las credenciales ni los datos reales de ninguna instalación.

Los modos admitidos son:

- red local privada y confiable;
- tailnet de Tailscale para acceso entre redes diferentes.

No se admite publicar directamente en Internet los puertos del dashboard, RTSP o HLS. Tailscale aporta transporte privado y control de pertenencia a la red, mientras BirdMonitor mantiene su propia autenticación y autorización.

## 2. Riesgos considerados

- acceso anónimo a audios, espectrogramas, ubicaciones o exportaciones;
- robo o reutilización de sesiones;
- peticiones CSRF contra acciones administrativas;
- uso del token del nodo para administrar recursos del usuario;
- path traversal y acceso a archivos fuera de los directorios permitidos;
- publicación o escucha anónima del streaming;
- exposición accidental de servicios en interfaces públicas;
- secretos incluidos en Git, logs, comandos o documentación;
- procesos que dependan de consolas abiertas;
- pérdida de contexto geográfico cuando un nodo cambia de ubicación.

## 3. Controles implementados

### 3.1 Usuario y sesión web

- contraseña administradora almacenada mediante hash;
- sesión firmada;
- cookie `HttpOnly` y `SameSite=Strict`;
- protección CSRF en operaciones que cambian estado;
- cierre de sesión mediante el método HTTP previsto, no mediante navegación `GET`;
- respuesta 401 para recursos privados solicitados sin sesión.

### 3.2 Autenticación y privilegios del nodo

- token Bearer exclusivo de la Raspberry, almacenado como hash en el servidor;
- permisos limitados a activación, ingesta, sincronización y control operativo necesarios;
- el nodo no recibe la contraseña administradora;
- el endpoint de contexto histórico devuelve solo identificadores mínimos y no expone credenciales ni coordenadas.

### 3.3 Protección de datos y archivos

- audios, espectrogramas, revisiones, analítica y exportaciones requieren sesión;
- extensiones y rutas de subida validadas;
- resolución de paths limitada a directorios autorizados;
- HLS se entrega mediante el backend después de comprobar la sesión;
- archivos de entorno reales excluidos del repositorio;
- plantillas versionadas sin secretos;
- credenciales de la Raspberry guardadas bajo `/etc/birdmonitor` con permisos restringidos.

### 3.4 Streaming

- identidades separadas para publicar, leer RTSP y usar el proxy HLS;
- publicación RTSP autenticada;
- RTSP ligado a la IP exacta del modo elegido;
- HLS ligado exclusivamente a loopback;
- APIs, métricas, playback y protocolos de MediaMTX no utilizados desactivados;
- el dashboard no recibe credenciales RTSP ni accede directamente a MediaMTX;
- procesos de backend y MediaMTX supervisados por tareas programadas y lanzados sin ventanas de consola visibles.

### 3.5 Red y firewall

- modo local limitado a la subred privada;
- modo Tailscale limitado al adaptador y rango de la tailnet;
- reglas de entrada dedicadas para dashboard y publicación RTSP;
- cabecera `Host` y origen comprobados según el modo configurado;
- no se abre HLS al exterior;
- no se requieren redirecciones de puertos en el router.

### 3.6 Disponibilidad segura al arrancar

La tarea de MediaMTX podía ejecutarse antes de que Windows recibiera su IP de Tailscale. En ese caso el enlace seguro fallaba y el proceso terminaba. Se corrigió el lanzador para esperar hasta tres minutos por la IP configurada antes de iniciar MediaMTX.

Se mantuvo el principio de mínima exposición: no se sustituyó el enlace exacto por `0.0.0.0`. La tarea continúa supervisada y puede reintentarse sin depender de una consola abierta.

### 3.7 Ubicaciones y privacidad

- sitio y despliegue se identifican mediante códigos y UUID, no mediante IP;
- cada evento conserva una instantánea del contexto con el que fue capturado;
- la cola offline no adopta retroactivamente la ubicación vigente al reenviar;
- las coordenadas pueden declarar su fuente e incertidumbre;
- el despliegue de Algeciras usa una referencia manual con 150 m de incertidumbre y no afirma contener el GPS exacto del micrófono.

### 3.8 Cambio remoto de ubicación

- el selector histórico no tiene permiso para cambiar el lugar físico del nodo;
- la acción administrativa aparece después de autenticar al usuario y exige una confirmación explícita de que la caja ya está en el sitio elegido;
- la petición usa sesión, protección CSRF y un catálogo cerrado de sitios con coordenadas válidas;
- el servidor crea una orden con UUID, usuario solicitante, instante, destino inmutable, número de entregas y estado (`pending`, `delivered`, `applied`, `failed` o `cancelled`);
- el token del nodo sólo puede recoger y confirmar órdenes del nodo principal; no puede crearlas, cancelarlas ni enumerar el historial administrativo;
- la Raspberry aplica el cambio únicamente entre ciclos, activa primero la campaña en el servidor, guarda después un JSON mediante reemplazo atómico y finalmente confirma el resultado;
- si no hay red o la activación no es aceptada, continúa con el sitio anterior; si se pierde el acuse final, reutiliza el mismo UUID y la misma fecha para completar el reintento;
- el modelo BirdNET y BirdWeather se reconstruyen tras el cambio usando las coordenadas del nuevo despliegue;
- los eventos que ya estaban en la cola offline conservan la instantánea geográfica previa.

## 4. Evidencia de verificación

La batería automatizada de esta revisión obtuvo:

```text
125 passed, 31 warnings
```

Las advertencias proceden de dependencias externas: detección opcional de
FFmpeg por Pydub y adaptadores de fecha de SQLite obsoletos en Python 3.12. No
se produjo ningún fallo de prueba.

Las pruebas cubren autenticación, CSRF, permisos del nodo, subida y recuperación de medios, streaming, modos de red, migración geográfica, aislamiento entre ubicaciones y el protocolo remoto con reintentos y persistencia atómica.

En la verificación operativa:

- `/health` confirmó seguridad, red y streaming configurados;
- `/login` respondió sin sesión y `/` rechazó el acceso anónimo;
- RTSP escuchó solo en la interfaz Tailscale;
- HLS escuchó solo en loopback;
- la Raspberry publicó el audio autenticado;
- el backend y MediaMTX permanecieron bajo supervisión automática;
- las colas offline quedaron vacías;
- SQLite devolvió integridad correcta y cero errores de claves foráneas.

La migración geográfica, el aislamiento por despliegue y el control remoto se
conservan como comportamiento verificable mediante las pruebas automatizadas
de ubicación, migración y nodo. Los informes de fase usados durante el
desarrollo no forman parte de la distribución instalable.

## 5. Gestión de secretos durante la intervención

- no se imprimieron tokens, hashes ni contraseñas;
- la clave Wi-Fi se introdujo silenciosamente en la Raspberry y no se incorporó al chat;
- antes de modificar el entorno del nodo se creó una copia con permisos restringidos;
- la clave SSH de despliegue fue temporal y se retiró al terminar;
- las copias de base de datos incluyeron hash SHA-256, comprobación de integridad y auditoría de la operación.

## 6. Limitaciones y mejoras futuras

- HTTPS sigue siendo recomendable si el modo local se usa en una red compartida;
- faltan rate limiting global y cuotas de almacenamiento;
- conviene cifrar y probar periódicamente la restauración de copias externas;
- deben revisarse dependencias y sistemas operativos de forma periódica;
- un administrador del servidor o de la Raspberry puede acceder a los datos y secretos de su propio equipo;
- una Raspberry comprometida puede enviar observaciones falsas con su identidad y requiere revocar y rotar su token.

Las instrucciones de instalación están en [`INSTALACION.md`](INSTALACION.md) y la política resumida del proyecto en [`../SECURITY.md`](../SECURITY.md).
