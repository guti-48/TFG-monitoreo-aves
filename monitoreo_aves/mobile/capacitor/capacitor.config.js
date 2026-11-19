// La app carga el dashboard desde el servidor (rutas relativas y cookies de sesion siguen funcionando).
// Cambiar destino: BIRDMONITOR_SERVER_URL=http://100.x.y.z:8000 npx cap sync
const url = process.env.BIRDMONITOR_SERVER_URL || 'http://127.0.0.1:8000';

module.exports = {
  appId: 'es.birdmonitor.app',
  appName: 'BirdMonitor',
  webDir: 'www',
  // Los margenes seguros los gestiona mobile.css con env(safe-area-inset-*); el fondo coincide con --bg-base.
  ios: { contentInset: 'never', backgroundColor: '#f4f6f1' },
  server: {
    url,
    // shortcut: HTTP en claro solo mientras no haya HTTPS; quitar al forzar HTTPS.
    cleartext: url.startsWith('http://'),
  },
};
