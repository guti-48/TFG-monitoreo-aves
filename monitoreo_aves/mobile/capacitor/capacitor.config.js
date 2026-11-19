// La app carga el dashboard desde el servidor (rutas relativas y cookies de sesion siguen funcionando).
// Cambiar destino: BIRDMONITOR_SERVER_URL=http://100.x.y.z:8000 npx cap sync
const url = process.env.BIRDMONITOR_SERVER_URL || 'http://127.0.0.1:8000';

module.exports = {
  appId: 'es.birdmonitor.app',
  appName: 'BirdMonitor',
  webDir: 'www',
  // Los margenes seguros los gestiona mobile.css con env(safe-area-inset-*); el fondo coincide con --bg-base.
  // La pantalla de arranque se oculta cuando el dashboard carga (mobile.js); 4 s como maximo si no llega a cargar.
  plugins: { SplashScreen: { launchAutoHide: true, launchShowDuration: 4000, backgroundColor: '#f0ebe2', showSpinner: false } },
  ios: { contentInset: 'never', backgroundColor: '#f0ebe2' },
  server: {
    url,
    // shortcut: HTTP en claro solo mientras no haya HTTPS; quitar al forzar HTTPS.
    cleartext: url.startsWith('http://'),
  },
};
