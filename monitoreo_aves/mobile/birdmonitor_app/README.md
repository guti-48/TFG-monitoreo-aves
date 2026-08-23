# Cliente Flutter legado

Esta carpeta conserva el antiguo prototipo móvil de BirdMonitor únicamente como referencia histórica.

## Estado

| Aspecto | Situación |
|---|---|
| Desarrollo de nuevas funciones | Detenido |
| Cliente recomendado | Dashboard web responsive servido por FastAPI |
| Instalación necesaria en móvil | Ninguna; se abre la URL privada en el navegador |
| Compatibilidad futura | No garantizada |

La experiencia se centralizó en la web para ofrecer desde una sola interfaz:

- autenticación y protección CSRF;
- detecciones, filtros y analítica;
- revisión de audio original/limpio;
- exportación CSV/XLSX;
- selección histórica de ubicaciones;
- escucha HLS protegida.

Mantener dos clientes completos duplicaría lógica, pruebas y superficie de ataque. Por ese motivo, este código no forma parte del procedimiento de instalación actual.

Consulta el [README principal](../../README.md) para desplegar y utilizar BirdMonitor.
