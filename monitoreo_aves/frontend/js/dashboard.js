const API_URL = "/detections/";
const IMG_BASE_URL = "/spectrograms/";
const ASSETS_PATH = 'assets/';
const NOISE_MAP = {
    'Human vocal': 'human.png',
    'Motor': 'ruido_amb.png',
};
const PLACEHOLDER_IMG = ASSETS_PATH + 'placeholder.jpg';

// Stream HLS servido por MediaMTX.
// El dashboard se sirve en el puerto 8000 y MediaMTX en el 8888.
// Se usa el mismo hostname para que funcione tanto con 127.0.0.1 como con la IP Tailscale.
const STREAM_NAME = "birdmonitor-audio";
const MEDIAMTX_HLS_PORT = 8888;
const LIVE_STREAM_URL = "http://127.0.0.1:8888/birdmonitor-audio/index.m3u8";
const LIVE_STREAM_PAGE_URL = `${window.location.protocol}//${window.location.hostname}:${MEDIAMTX_HLS_PORT}/${STREAM_NAME}/`;
const STREAM_CONTROL_URL = "/stream/control";
const STREAM_NODE_NAME = "birdmonitor";


let hlsInstance = null;
let liveAudioContext = null;
let liveAnalyser = null;
let liveSourceNode = null;
let liveSourceAudio = null;
let liveSpectrumFrame = null;
let liveSpectrumData = null;

let currentView = 'dashboard';
let activeNodeFilter = null;
let myChart = null;
let intervalId = null;
let liveHls = null;
let streamStatusTimer = null;
let lastStreamData = null;
let currentScienceReport = [];

// NAVEGACIÓ
function switchView(viewName, nodeFilter = null) {
    if (currentView === 'live' && viewName !== 'live') {
        cleanupLiveStream();
    }

    currentView = viewName;
    activeNodeFilter = nodeFilter;

    ['btn-dashboard', 'btn-live', 'btn-nodes', 'btn-history', 'btn-science', 'btn-daily'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.className = 'nav-link';
    });

    const map = {
        dashboard: 'btn-dashboard',
        live: 'btn-live',
        history: 'btn-history',
        nodes: 'btn-nodes',
        science: 'btn-science',
        daily: 'btn-daily'
    };

    const titleMap = {
        dashboard: 'Monitorización Global',
        live: 'Escucha en directo',
        history: 'Histórico de detecciones',
        nodes: 'Red de Nodos',
        science: 'Análisis Ecológico',
        daily: 'Informe Diario'
    };

    const active = document.getElementById(map[viewName]);
    if (active) active.className = 'nav-link active';

    safeSetText('topbar-view-title', titleMap[viewName] || 'Monitorización Global');

    const container = document.getElementById('main-content');
    if (!container) return;

    container.className = 'd-flex flex-column flex-grow-1 w-100';
    if (viewName === 'history') container.classList.add('view-history');

    if (viewName === 'dashboard') { container.innerHTML = getDashboardHTML(); updateDashboard(); }
    else if (viewName === 'live') renderLiveStreamView(container);
    else if (viewName === 'history') renderHistoryView(container);
    else if (viewName === 'nodes') renderNodesView(container);
    else if (viewName === 'science') renderScienceView(container);
    else if (viewName === 'daily') renderDailyView(container);
}

// ESCUCHA EN DIRECTO
function renderLiveStreamView(container) {
    cleanupLiveStream();

    container.innerHTML = `
        <div class="row justify-content-center animate-fade-in">
            <div class="col-12 col-xl-9">
                <div class="card live-stream-card live-console">
                    <div class="card-body">
                        <div class="live-console-head">
                            <div class="live-stream-hero">
                                <div class="live-stream-icon">
                                    <i class="bi bi-soundwave"></i>
                                </div>
                                <div class="min-w-0">
                                    <p class="text-muted small text-uppercase fw-bold mb-1">Escucha en directo</p>
                                    <h4 class="fw-bold text-white mb-1">${STREAM_NAME}</h4>
                                    <p class="text-muted mb-0 small">
                                        <span id="live-hls-url" class="font-monospace">${LIVE_STREAM_URL}</span>
                                    </p>
                                </div>
                            </div>
                            <span id="live-stream-status" class="badge bg-secondary px-3 py-2">
                                <i class="bi bi-circle-fill me-1"></i>Consultando...
                            </span>
                        </div>

                        <div class="live-player-shell">
                            <div class="audio-panel live-audio-panel">
                                <audio id="live-audio-player" class="w-100" controls preload="none" crossorigin="anonymous"></audio>
                            </div>

                            <div class="live-spectrum-panel">
                                <div class="live-spectrum-head">
                                    <span><i class="bi bi-soundwave me-1"></i>Espectro en directo</span>
                                    <small id="live-spectrum-state">Esperando audio</small>
                                </div>
                                <canvas id="live-spectrum-canvas" width="900" height="220"></canvas>
                            </div>
                        </div>

                        <div class="live-actions">
                            <button class="btn btn-success" onclick="setLiveStreamEnabled(true)">
                                <i class="bi bi-broadcast me-2"></i>Activar escucha
                            </button>
                            <button class="btn btn-outline-info" onclick="initLiveStreamPlayer(true)">
                                <i class="bi bi-headphones me-2"></i>Conectar reproductor
                            </button>
                            <button class="btn btn-outline-secondary" onclick="setLiveStreamEnabled(false)">
                                <i class="bi bi-stop-circle me-2"></i>Detener escucha
                            </button>
                        </div>

                        <p id="live-stream-message" class="text-muted small mb-0 mt-3">
                            Activa el servicio en la Raspberry; despues conecta el reproductor HLS para escuchar y ver el espectro.
                        </p>

                        <div class="live-mini-note">
                            Activar arranca el servicio en la Raspberry. Conectar enlaza este navegador al stream HLS.
                        </div>
                    </div>
                </div>
            </div>
        </div>`;

    refreshLiveStreamControlStatus();

    streamStatusTimer = setInterval(() => {
        if (currentView === 'live') {
            refreshLiveStreamControlStatus();
        }
    }, 5000);
}

function setLiveStreamStatus(type, text) {
    const status = document.getElementById('live-stream-status');
    if (!status) return;

    const classes = {
        online: 'badge bg-success px-3 py-2',
        warning: 'badge bg-warning px-3 py-2',
        offline: 'badge bg-danger px-3 py-2',
        checking: 'badge bg-secondary px-3 py-2'
    };

    const icons = {
        online: 'bi-check-circle-fill',
        warning: 'bi-exclamation-triangle-fill',
        offline: 'bi-x-circle-fill',
        checking: 'bi-circle-fill'
    };

    status.className = classes[type] || classes.checking;
    status.innerHTML = `<i class="bi ${icons[type] || icons.checking} me-1"></i>${text}`;
}

function setLiveStreamMessage(text, isError = false) {
    const message = document.getElementById('live-stream-message');
    if (!message) return;
    message.className = isError ? 'text-danger small mb-0 mt-3' : 'text-muted small mb-0 mt-3';
    message.textContent = text;
}

async function fetchLiveStreamControlStatus() {
    const response = await fetch(
        `${STREAM_CONTROL_URL}?node_name=${encodeURIComponent(STREAM_NODE_NAME)}&t=${Date.now()}`,
        { cache: 'no-store' }
    );

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
}

async function refreshLiveStreamControlStatus() {
    try {
        const data = await fetchLiveStreamControlStatus();
        lastStreamData = data;

        const hlsUrl = LIVE_STREAM_URL;
        const pageUrl = data.page_url || LIVE_STREAM_PAGE_URL;

        const hlsLabel = document.getElementById('live-hls-url');
        const directLink = document.getElementById('live-stream-page-link');
        const desired = document.getElementById('stream-desired-state');
        const real = document.getElementById('stream-real-state');
        const lastStatus = document.getElementById('stream-last-status');
        const detail = document.getElementById('live-stream-detail');

        if (hlsLabel) hlsLabel.textContent = hlsUrl;
        if (directLink) directLink.href = pageUrl;

        if (desired) desired.textContent = data.stream_enabled ? 'Activado' : 'Desactivado';
        if (real) real.textContent = data.actual_running ? 'Ejecutándose' : 'Detenido';
        if (lastStatus) lastStatus.textContent = data.last_status_at || '-';

        if (detail) {
            detail.innerHTML = `
                <div><strong>Detalle:</strong> ${data.detail || 'Sin detalle'}</div>
                <div><strong>HLS:</strong> <span class="font-monospace">${hlsUrl}</span></div>
                <div><strong>Actualizado:</strong> ${data.updated_at || '-'}</div>
            `;
        }

        if (data.actual_running) {
            setLiveStreamStatus('online', 'Stream activo');
            setLiveStreamMessage('El servicio de streaming está activo. Puedes conectar el reproductor.');
        } else if (data.stream_enabled && !data.actual_running) {
            setLiveStreamStatus('warning', 'Arrancando...');
            setLiveStreamMessage('El backend ha solicitado activar la escucha. Esperando reporte de la Raspberry.');
        } else {
            setLiveStreamStatus('checking', 'Stream detenido');
            setLiveStreamMessage('La escucha está desactivada. Pulsa “Activar escucha” para arrancar birdstream.service.');
        }

    } catch (e) {
        setLiveStreamStatus('offline', 'Error backend');
        setLiveStreamMessage(`No se pudo consultar /stream/control: ${e.message}`, true);

        const detail = document.getElementById('live-stream-detail');
        if (detail) {
            detail.textContent = `Error consultando el estado del streaming: ${e.message}`;
        }
    }
}

async function setLiveStreamEnabled(enabled) {
    try {
        setLiveStreamStatus('checking', enabled ? 'Activando...' : 'Deteniendo...');
        setLiveStreamMessage(enabled
            ? 'Solicitando a la Raspberry que arranque birdstream.service...'
            : 'Solicitando a la Raspberry que detenga birdstream.service...'
        );

        const response = await fetch(STREAM_CONTROL_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                node_name: STREAM_NODE_NAME,
                stream_enabled: enabled
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        lastStreamData = await response.json();
        await refreshLiveStreamControlStatus();

        if (enabled) {
            setTimeout(async () => {
                await refreshLiveStreamControlStatus();
                if (lastStreamData && lastStreamData.actual_running) {
                    initLiveStreamPlayer(true);
                }
            }, 6000);
        } else {
            stopLiveStreamPlayer();
        }

    } catch (e) {
        setLiveStreamStatus('offline', 'Error');
        setLiveStreamMessage(`No se pudo cambiar el estado del streaming: ${e.message}`, true);
    }
}

function getCurrentHlsUrl() {
    return LIVE_STREAM_URL;
}

function initLiveStreamPlayer(autoplay = false) {
    const audio = document.getElementById('live-audio-player');
    if (!audio) return;

    audio.crossOrigin = 'anonymous';
    audio.onplay = () => startLiveSpectrum(audio);
    audio.onpause = () => setLiveSpectrumState('Pausado');

    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }

    const hlsUrl = getCurrentHlsUrl();

    setLiveStreamStatus('checking', 'Conectando...');
    setLiveStreamMessage('Conectando con el flujo HLS de MediaMTX...');

    if (window.Hls && Hls.isSupported()) {
        hlsInstance = new Hls({
            enableWorker: true,
            lowLatencyMode: true,
            backBufferLength: 30
        });

        hlsInstance.loadSource(hlsUrl);
        hlsInstance.attachMedia(audio);

        hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
            setLiveStreamStatus('online', 'Stream disponible');
            setLiveStreamMessage('Stream cargado. Usa el reproductor para escuchar en directo.');
            startLiveSpectrum(audio);
            if (autoplay) {
                audio.play().catch(() => {
                    setLiveStreamMessage('El navegador bloqueó la reproducción automática. Pulsa play manualmente.');
                });
            }
        });

        hlsInstance.on(Hls.Events.ERROR, (_, data) => {
            if (!data || !data.fatal) return;

            setLiveStreamStatus('offline', 'Stream no disponible');
            setLiveStreamMessage('No se pudo cargar el stream HLS. Comprueba MediaMTX y birdstream.service.', true);

            if (hlsInstance) {
                hlsInstance.destroy();
                hlsInstance = null;
            }
        });

        return;
    }

    if (audio.canPlayType('application/vnd.apple.mpegurl')) {
        audio.src = hlsUrl;
        audio.addEventListener('loadedmetadata', () => {
            setLiveStreamStatus('online', 'Stream disponible');
            setLiveStreamMessage('Stream cargado mediante soporte HLS nativo.');
            startLiveSpectrum(audio);
            if (autoplay) {
                audio.play().catch(() => {
                    setLiveStreamMessage('El navegador bloqueó la reproducción automática. Pulsa play manualmente.');
                });
            }
        }, { once: true });
        return;
    }

    setLiveStreamStatus('warning', 'HLS no soportado');
    setLiveStreamMessage('Este navegador no soporta HLS directamente. Abre MediaMTX en una pestaña nueva.', true);
}

function setLiveSpectrumState(text) {
    const el = document.getElementById('live-spectrum-state');
    if (el) el.textContent = text;
}

function startLiveSpectrum(audio) {
    const canvas = document.getElementById('live-spectrum-canvas');
    if (!canvas || !audio) return;

    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) {
            setLiveSpectrumState('No soportado');
            return;
        }

        if (!liveAudioContext) {
            liveAudioContext = new AudioCtx();
        }

        if (!liveAnalyser) {
            liveAnalyser = liveAudioContext.createAnalyser();
            liveAnalyser.fftSize = 2048;
            liveAnalyser.smoothingTimeConstant = 0.72;
            liveSpectrumData = new Uint8Array(liveAnalyser.frequencyBinCount);
        }

        if (!liveSourceNode || liveSourceAudio !== audio) {
            if (liveSourceNode) {
                try {
                    liveSourceNode.disconnect();
                } catch (_) {}
            }
            liveSourceNode = liveAudioContext.createMediaElementSource(audio);
            liveSourceAudio = audio;
            liveSourceNode.connect(liveAnalyser);
            liveAnalyser.connect(liveAudioContext.destination);
        }

        liveAudioContext.resume().catch(() => {});
        setLiveSpectrumState('Analizando');

        if (liveSpectrumFrame) {
            cancelAnimationFrame(liveSpectrumFrame);
            liveSpectrumFrame = null;
        }

        drawLiveSpectrum(canvas);

    } catch (e) {
        setLiveSpectrumState('Sin visualizacion');
    }
}

function drawLiveSpectrum(canvas) {
    if (!liveAnalyser || !liveSpectrumData || !canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    liveAnalyser.getByteFrequencyData(liveSpectrumData);

    ctx.drawImage(canvas, 1, 0, width - 1, height, 0, 0, width - 1, height);
    ctx.fillStyle = '#f4f6f1';
    ctx.fillRect(width - 2, 0, 2, height);

    for (let y = 0; y < height; y++) {
        const normalized = 1 - (y / height);
        const index = Math.min(
            liveSpectrumData.length - 1,
            Math.floor(normalized * normalized * liveSpectrumData.length)
        );
        const value = liveSpectrumData[index] / 255;
        const hue = 135 + (value * 70);
        const saturation = 24 + (value * 42);
        const lightness = 91 - (value * 52);

        ctx.fillStyle = `hsl(${hue}, ${saturation}%, ${lightness}%)`;
        ctx.fillRect(width - 2, y, 2, 1);
    }

    liveSpectrumFrame = requestAnimationFrame(() => drawLiveSpectrum(canvas));
}

function stopLiveSpectrum(release = false) {
    if (liveSpectrumFrame) {
        cancelAnimationFrame(liveSpectrumFrame);
        liveSpectrumFrame = null;
    }

    if (release) {
        if (liveSourceNode) {
            try {
                liveSourceNode.disconnect();
            } catch (_) {}
            liveSourceNode = null;
            liveSourceAudio = null;
        }

        if (liveAnalyser) {
            try {
                liveAnalyser.disconnect();
            } catch (_) {}
            liveAnalyser = null;
        }

        liveSpectrumData = null;
    }

    setLiveSpectrumState('Detenido');
}

function stopLiveStreamPlayer() {
    const audio = document.getElementById('live-audio-player');

    stopLiveSpectrum();

    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }

    if (audio) {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
    }

    setLiveStreamMessage('Reproducción detenida en este navegador.');
}

function cleanupLiveStream() {
    stopLiveStreamPlayer();
    stopLiveSpectrum(true);

    if (streamStatusTimer) {
        clearInterval(streamStatusTimer);
        streamStatusTimer = null;
    }
}

// HISTÓRICO
async function renderHistoryView(container) {
    container.innerHTML = `<div class="d-flex justify-content-center align-items-center py-5"><div class="spinner-border text-success" role="status"></div><span class="ms-3 text-muted">Cargando base de datos completa...</span></div>`;
    try {
        const response = await fetch(`${API_URL}?limit=500`);
        const data = await response.json();
        const sortedData = data.reverse();
        let rowsHtml = '';
        sortedData.forEach(d => {
            const timeDate = new Date(d.timestamp);
            const dateStr = timeDate.toLocaleDateString();
            const timeStr = timeDate.toLocaleTimeString();
            const imgUrl = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
            const clean = cleanName(d.species);
            let icon = '<i class="bi bi-music-note-beamed text-success"></i>';
            if (d.species.includes("Human") || d.species.includes("Motor") || d.species.includes("Noise"))
                icon = '<i class="bi bi-boombox text-warning"></i>';
            rowsHtml += `
            <tr>
                <td class="text-white-50 small">${d.id}</td>
                <td>${dateStr} <small class="text-muted">${timeStr}</small></td>
                <td><div class="d-flex align-items-center"><div class="me-2">${icon}</div><span class="fw-bold text-white">${clean}</span></div></td>
                <td>${d.device_name || 'RaspberryPi'}</td>
                <td><div class="progress" style="height:6px;width:100px;"><div class="progress-bar bg-${d.confidence > 0.8 ? 'success' : 'warning'}" role="progressbar" style="width:${d.confidence * 100}%"></div></div></td>
                <td><a href="${imgUrl}" target="_blank" class="btn btn-sm btn-outline-secondary"><i class="bi bi-image"></i> Ver</a></td>
            </tr>`;
        });
        container.innerHTML = `
            <div class="row mb-4 animate-fade-in">
                <div class="col-12 d-flex justify-content-between align-items-center">
                    <div>
                        <h3 class="fw-bold text-white"><i class="bi bi-database-fill me-2 text-accent"></i>Histórico</h3>
                        <p class="text-muted mb-0">Total registros: ${sortedData.length}</p>
                    </div>
                    <button class="btn btn-success" onclick="downloadCSV()"><i class="bi bi-file-earmark-spreadsheet me-2"></i>Exportar Excel</button>
                </div>
            </div>
            <div class="card bg-dark shadow-sm border-0 flex-grow-1 d-flex flex-column animate-fade-in history-card-container">
                <div class="card-body p-0 d-flex flex-column">
                    <div class="table-container">
                        <table class="table table-dark table-hover mb-0">
                            <thead class="table-sticky-header">
                                <tr><th class="py-3 ps-3">ID</th><th class="py-3">Fecha</th><th class="py-3">Especie</th><th class="py-3">Nodo</th><th class="py-3">Confianza</th><th class="py-3 pe-3">Foto</th></tr>
                            </thead>
                            <tbody>${rowsHtml}</tbody>
                        </table>
                    </div>
                </div>
            </div>`;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
}

//DASHBOARD TIEMPO REAL
async function updateDashboard() {
    if (currentView !== 'dashboard') return;
    try {
        const response = await fetch(`${API_URL}?t=${new Date().getTime()}`, { cache: 'no-store' });
        let data = await response.json();
        if (!data || data.length === 0) { safeSetText('total-counter', '0'); return; }

        const sortedData = data;
        let totalAmp = 0;
        sortedData.forEach(d => { totalAmp += (d.amplitude || 0); });
        let avgAmp = (sortedData.length > 0) ? (totalAmp / sortedData.length) * 500 : 0;
        if (avgAmp > 100) avgAmp = 100;

        let noiseLabel = "Silencioso", noiseColor = "success", noiseIcon = "bi-tree-fill";
        if (avgAmp > 10) { noiseLabel = "Moderado"; noiseColor = "warning"; noiseIcon = "bi-people-fill"; }
        if (avgAmp > 30) { noiseLabel = "Ruidoso"; noiseColor = "danger"; noiseIcon = "bi-speaker-fill"; }

        const noiseEl = document.getElementById('noise-metric');
        if (noiseEl) {
            noiseEl.innerText = `${noiseLabel} (Vol: ${avgAmp.toFixed(0)})`;
            noiseEl.className = `fw-bold mb-0 fs-5 text-${noiseColor}`;
            document.getElementById('noise-card').className = `kpi-item kpi-item-${noiseColor}`;
            document.getElementById('noise-icon-box').className = `icon-box bg-${noiseColor}-subtle text-${noiseColor}`;
            document.getElementById('noise-icon').className = `bi ${noiseIcon} fs-3`;
        }

        const birdsOnly = sortedData.filter(d =>
            !d.species.toLowerCase().includes("noise") &&
            !d.species.toLowerCase().includes("ruido") &&
            !d.species.toLowerCase().includes("ambiente")
        );
        safeSetText('total-counter', birdsOnly.length);

        if (birdsOnly.length > 0) {
            const latestBird = birdsOnly[0];
            safeSetText('last-activity', new Date(latestBird.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
            const counts = {};
            birdsOnly.forEach(d => { counts[d.species] = (counts[d.species] || 0) + 1; });
            const topSpecies = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
            safeSetText('top-species', cleanName(topSpecies));
            if (typeof renderLiveFeedSplit === "function") await renderLiveFeedSplit(latestBird);
            if (typeof renderTable === "function") renderTable(birdsOnly.slice(0, 10));
            if (typeof updateChart === "function") updateChart(counts);
        }
    } catch (error) { console.error("Error Dashboard:", error); }
}

function getDashboardHTML() {
    return `
    <section class="card kpi-panel mb-4 animate-fade-in">
        <div class="kpi-grid">
            <div class="kpi-item kpi-item-success">
                <div class="kpi-content">
                    <div>
                        <p class="text-muted small text-uppercase mb-1 fw-bold">Detecciones Totales</p>
                        <h3 class="fw-bold mb-0" id="total-counter">0</h3>
                    </div>
                    <div class="icon-box bg-success-subtle text-success"><i class="bi bi-soundwave fs-3"></i></div>
                </div>
            </div>
            <div class="kpi-item kpi-item-earth">
                <div class="kpi-content">
                    <div>
                        <p class="text-muted small text-uppercase mb-1 fw-bold">Especie Dominante</p>
                        <h4 class="fw-bold mb-0 fs-5 text-truncate" id="top-species">-</h4>
                    </div>
                    <div class="icon-box bg-earth-subtle text-earth"><i class="bi bi-trophy-fill fs-3"></i></div>
                </div>
            </div>
            <div class="kpi-item kpi-item-info">
                <div class="kpi-content">
                    <div>
                        <p class="text-muted small text-uppercase mb-1 fw-bold">Última Actividad</p>
                        <h4 class="fw-bold mb-0 fs-5" id="last-activity">--:--</h4>
                    </div>
                    <div class="icon-box bg-info-subtle text-info"><i class="bi bi-clock-history fs-3"></i></div>
                </div>
            </div>
            <div class="kpi-item kpi-item-secondary" id="noise-card">
                <div class="kpi-content">
                    <div>
                        <p class="text-muted small text-uppercase mb-1 fw-bold">Nivel de Ruido</p>
                        <h4 class="fw-bold mb-0 fs-5" id="noise-metric">Calculando...</h4>
                    </div>
                    <div class="icon-box bg-secondary-subtle" id="noise-icon-box"><i class="bi bi-boombox fs-3" id="noise-icon"></i></div>
                </div>
            </div>
        </div>
    </section>

    <div class="row g-4 mb-5">
        <div class="col-lg-7">
            <div class="card shadow-sm border-0 bg-dark overflow-hidden dashboard-live-card" style="min-height:420px;">
                <div class="card-body p-0 d-flex flex-column h-100" id="live-feed-container">
                    <div class="empty-detection-state">
                        <div class="empty-detection-icon"><i class="bi bi-radar"></i></div>
                        <p class="mb-1 fw-semibold">Esperando detecciones...</p>
                        <span>El nodo mostrará aquí la última fuente acústica identificada.</span>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-lg-5">
            <div class="card h-100 shadow-sm border-0 chart-card">
                <div class="card-header bg-transparent border-0 py-3">
                    <h5 class="fw-bold m-0"><i class="bi bi-pie-chart-fill me-2 text-accent"></i>Distribución de Especies</h5>
                </div>
                <div class="card-body"><canvas id="speciesChart" style="max-height:300px;"></canvas></div>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-12">
            <div class="card shadow-sm border-0 bg-dark recent-table-card">
                <div class="card-header bg-transparent border-0 py-3">
                    <h5 class="fw-bold text-white m-0"><i class="bi bi-list-check me-2 text-accent"></i>Registro Reciente</h5>
                </div>
                <div class="table-responsive">
                    <table class="table table-dark table-hover align-middle mb-0">
                        <thead class="bg-dark-subtle text-uppercase small">
                            <tr><th class="ps-4">Hora</th><th>Especie</th><th>Confianza</th><th>Espectrograma</th><th class="text-end pe-4">ID</th></tr>
                        </thead>
                        <tbody id="history-table-body"></tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>`;
}

function csvCell(value) {
    if (value === null || value === undefined) return '';
    const text = Array.isArray(value) ? value.join(' | ') : String(value);
    return `"${text.replace(/"/g, '""')}"`;
}

function downloadTableCSV(filename, headers, rows) {
    const csvRows = [
        'sep=;',
        headers.map(csvCell).join(';'),
        ...rows.map(row => row.map(csvCell).join(';'))
    ];

    const blob = new Blob([`\ufeff${csvRows.join('\r\n')}`], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
}

async function downloadCSV() {
    try {
        const response = await fetch(`${API_URL}?limit=1000`);
        const data = await response.json();
        if (!data || data.length === 0) { alert("Sin datos"); return; }

        const rows = data.map(row => {
            const dateObj = new Date(row.timestamp);
            return [
                row.id,
                dateObj.toLocaleDateString(),
                dateObj.toLocaleTimeString(),
                row.timestamp,
                cleanName(row.species),
                row.confidence,
                row.amplitude ?? '',
                row.device_name || row.device_id || '',
                row.filename
            ];
        });

        downloadTableCSV(
            `birdmonitor_detecciones_${new Date().toISOString().slice(0, 10)}.csv`,
            ['ID', 'Fecha', 'Hora', 'Timestamp_ISO', 'Especie', 'Confianza', 'Amplitud_RMS', 'Nodo_o_Device_ID', 'Archivo_WAV'],
            rows
        );
    } catch (e) { alert("Error exportando"); }
}

async function getSpeciesImageUrl(speciesRawName) {
    let clean = speciesRawName;
    if (speciesRawName.includes('_')) clean = speciesRawName.split('_')[1];
    clean = clean.replace(/_/g, ' ').trim();
    if (NOISE_MAP[clean] || clean.includes("Human") || clean.includes("Motor") || clean.includes("Noise")) {
        if (clean.includes("Human")) return ASSETS_PATH + 'human.png';
        if (clean.includes("Motor") || clean.includes("Ruido") || clean.includes("Noise")) return ASSETS_PATH + 'ruido_amb.png';
        return PLACEHOLDER_IMG;
    }
    const WIKI_EXACT_PAGES = { 'Merlin': 'Merlin (bird)', 'Kite': 'Kite (bird)' };
    let searchTitle = WIKI_EXACT_PAGES[clean] || clean;
    try {
        const wikiUrl = `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(searchTitle)}&prop=pageimages&format=json&pithumbsize=600&redirects=1&origin=*`;
        const res = await fetch(wikiUrl);
        const data = await res.json();
        const pages = data.query.pages;
        const pageId = Object.keys(pages)[0];
        if (pageId !== "-1" && pages[pageId].thumbnail) return pages[pageId].thumbnail.source;
    } catch (e) { console.error("Error Wiki", e); }
    return PLACEHOLDER_IMG;
}

async function renderLiveFeedSplit(d) {
    const container = document.getElementById('live-feed-container');
    if (!container) return;
    const species = cleanName(d.species);
    const percent = (d.confidence * 100).toFixed(0);
    const spectrogramUrl = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
    const timeStr = new Date(d.timestamp).toLocaleTimeString();
    const speciesPhotoUrl = await getSpeciesImageUrl(d.species);

    container.innerHTML = `
        <div class="main-detection-split enhanced-detection w-100">
            <div class="split-photo">
                <img src="${speciesPhotoUrl}" class="bird-photo" onerror="this.src='${PLACEHOLDER_IMG}'">
                <div class="photo-overlay-label"><i class="bi bi-camera-fill me-2"></i>Imagen de Referencia</div>
            </div>
            <div class="split-info">
                <h6 class="text-muted text-uppercase fw-bold mb-1">Detección en vivo - ${timeStr}</h6>
                <h2 class="display-6 fw-bold text-white mb-3 text-truncate" title="${species}">${species}</h2>
                <div class="d-flex align-items-center mb-4 w-100">
                    <span class="badge bg-success me-3 fs-6 px-3 py-2">${percent}% Confianza</span>
                    <div class="progress w-100" style="height:12px;background-color:rgba(255,255,255,0.2);">
                        <div class="progress-bar bg-success progress-bar-striped progress-bar-animated" role="progressbar" style="width:${percent}%;"></div>
                    </div>
                </div>
                <div class="spectrogram-container mt-auto d-flex flex-column">
                    <img src="${spectrogramUrl}" class="spectrogram-img" onerror="this.style.opacity='0.3';">
                    <div class="bg-dark text-muted small px-3 py-2 d-flex justify-content-between align-items-center border-top border-secondary mt-auto">
                        <span><i class="bi bi-soundwave me-2"></i>Espectrograma</span>
                        <span class="font-monospace text-white-50 text-truncate" style="max-width:50%;" title="${d.filename}">${d.filename}</span>
                    </div>
                </div>
            </div>
        </div>`;
}

function renderTable(data) {
    const tbody = document.getElementById('history-table-body');
    if (!tbody) return;
    tbody.innerHTML = "";
    data.forEach(d => {
        const imgUrl = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
        const clean = cleanName(d.species);
        let icon = '<i class="bi bi-feather text-success me-2"></i>';
        if (NOISE_MAP[clean] || d.species.includes("Human") || d.species.includes("Motor"))
            icon = '<i class="bi bi-boombox text-muted me-2"></i>';
        tbody.innerHTML += `<tr><td class="ps-4 fw-bold text-muted">${new Date(d.timestamp).toLocaleTimeString()}</td><td><div class="d-flex align-items-center">${icon}<span class="fw-semibold text-white">${clean}</span></div></td><td><span class="badge bg-dark-subtle text-success border">${(d.confidence * 100).toFixed(0)}%</span></td><td><a href="${imgUrl}" target="_blank"><img src="${imgUrl}" class="table-img-preview" onerror="this.style.display='none'"></a></td><td class="text-end pe-4 text-muted small">#${d.id}</td></tr>`;
    });
}

function updateChart(counts) {
    const canvas = document.getElementById('speciesChart');
    if (!canvas) return;
    if (myChart) { myChart.destroy(); }
    const ctx = canvas.getContext('2d');
    const labels = Object.keys(counts).map(cleanName);
    const values = Object.values(counts);
    const natureColors = ['#2f6f4e', '#326f72', '#a66f2f', '#6f7f5a', '#405f82'];
    myChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: natureColors, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#5f6f65' } } } }
    });
}

function safeSetText(id, text) { const el = document.getElementById(id); if (el) el.innerText = text; }
function cleanName(name) { if (!name) return "Desconocido"; let cleaned = name.split('_')[1] || name; return cleaned.charAt(0).toUpperCase() + cleaned.slice(1); }


// TOOLTIP CUSTOM — se monta una sola vez en el body

(function mountTooltip() {
    const tt = document.createElement('div');
    tt.id = 'gauge-tooltip';
    tt.style.cssText = `
        position:fixed; z-index:9999; pointer-events:none;
        background:#ffffff; color:#1f2923; border:1px solid #c6d0c2;
        border-radius:8px; padding:8px 12px; font-size:0.75rem;
        max-width:260px; line-height:1.5; box-shadow:0 8px 22px rgba(31,41,35,0.14);
        opacity:0; transition:opacity 0.15s; font-family:'DM Sans',sans-serif;`;
    document.body.appendChild(tt);

    document.addEventListener('mouseover', e => {
        const el = e.target.closest('[data-gauge-tip]');
        if (!el) return;
        tt.textContent = el.dataset.gaugeTip;
        tt.style.opacity = '1';
    });
    document.addEventListener('mousemove', e => {
        if (tt.style.opacity === '0') return;
        let x = e.clientX + 14, y = e.clientY + 14;
        if (x + 270 > window.innerWidth) x = e.clientX - 274;
        if (y + 100 > window.innerHeight) y = e.clientY - 80;
        tt.style.left = x + 'px';
        tt.style.top = y + 'px';
    });
    document.addEventListener('mouseout', e => {
        if (!e.target.closest('[data-gauge-tip]')) return;
        const to = e.relatedTarget;
        if (to && to.closest('[data-gauge-tip]') === e.target.closest('[data-gauge-tip]')) return;
        tt.style.opacity = '0';
    });
})();

// GAUGE SVG
function buildGaugeSVG(value, min, max, color, label, tooltip) {
    const R = 52;
    const CX = 70, CY = 70;
    const startAngle = -210;
    const sweepTotal = 240;

    const clampedVal = Math.min(Math.max(value, min), max);
    const pct = (clampedVal - min) / (max - min);
    const sweepActive = sweepTotal * pct;

    function polarToXY(angleDeg, r) {
        const rad = (angleDeg - 90) * (Math.PI / 180);
        return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
    }
    function arcPath(fromDeg, toDeg, r) {
        const p1 = polarToXY(fromDeg, r);
        const p2 = polarToXY(toDeg, r);
        const large = (toDeg - fromDeg) > 180 ? 1 : 0;
        return `M ${p1.x} ${p1.y} A ${r} ${r} 0 ${large} 1 ${p2.x} ${p2.y}`;
    }

    const endAngle = startAngle + sweepTotal;
    const activeEnd = startAngle + sweepActive;
    const displayVal = (value % 1 === 0) ? value.toFixed(0) : value.toFixed(3);
    const textColor = pct >= 0.65 ? '#2f6f4e' : pct >= 0.35 ? '#a66f2f' : '#9c3f3f';
    const tipEscaped = tooltip.replace(/"/g, '&quot;');

    return `
    <div class="gauge-wrapper" data-gauge-tip="${tipEscaped}">
        <svg viewBox="0 0 140 100" width="140" height="100" xmlns="http://www.w3.org/2000/svg" style="pointer-events:none;">
            <path d="${arcPath(startAngle, endAngle, R)}"
                  fill="none" stroke="#dfe5db" stroke-width="10" stroke-linecap="round"/>
            <path d="${arcPath(startAngle, activeEnd, R)}"
                  fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round"
                  />
            <text x="${CX}" y="${CY - 4}" text-anchor="middle"
                  font-size="18" font-weight="700" fill="${textColor}" font-family="DM Sans,sans-serif">
                ${displayVal}
            </text>
            <text x="${CX}" y="${CY + 13}" text-anchor="middle"
                  font-size="9" fill="#879389" font-family="DM Sans,sans-serif" letter-spacing="1">
                ${label.toUpperCase()}
            </text>
            <text x="20"  y="92" text-anchor="middle" font-size="8" fill="#879389">${min}</text>
            <text x="120" y="92" text-anchor="middle" font-size="8" fill="#879389">${max % 1 === 0 ? max : max.toFixed(1)}</text>
        </svg>
        <p class="gauge-label">${label}</p>
    </div>`;
}

// VISTA ANÁLISIS ECO
async function renderScienceView(container) {
    container.innerHTML = `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="spinner-grow text-info" role="status"></div>
            <span class="ms-3 text-white">Procesando datos del nodo...</span>
        </div>`;
    try {
        const response = await fetch("http://100.98.248.58:8000/analytics/biodiversity");
        const report = await response.json();
        currentScienceReport = report || [];
        if (!report || report.length === 0) {
            container.innerHTML = `<div class="alert alert-warning text-center mt-4">Esperando detecciones reales del nodo...</div>`;
            return;
        }

        const r = report[0];

        const calidad = r.calidad || 'POBRE';
        const calidadUpper = calidad.toUpperCase();
        const calBadge = calidadUpper === 'EXCELENTE' ? 'success' : calidadUpper === 'MODERADO' ? 'warning' : 'danger';

        // ── Gauges biodiversidad — LAYOUT 3+2 
        const g1 = buildGaugeSVG(r.shannon, 0, 5, '#405f82', "Shannon H'",
            "Índice de Shannon-Wiener (H'): mide diversidad considerando riqueza y equitabilidad. >3 = Excelente, 1.5–3 = Moderado, <1.5 = Pobre.");
        const g2 = buildGaugeSVG(r.simpson, 0, 1, '#326f72', "Simpson 1-D",
            "Índice de Simpson (1-D): probabilidad de que dos individuos elegidos al azar pertenezcan a especies distintas. Próximo a 1 = alta diversidad.");
        const g3 = buildGaugeSVG(r.pielou, 0, 1, '#2f6f4e', "Pielou J'",
            "Índice de equitabilidad de Pielou (J'): uniformidad en la distribución de individuos entre especies. 1 = perfectamente equitativo.");
        const g4 = buildGaugeSVG(Math.min(r.riqueza, 30), 0, 30, '#a66f2f', "Riqueza S",
            "Riqueza específica (S): número de especies únicas detectadas. Indicador primario de biodiversidad.");
        const g5 = buildGaugeSVG(Math.min(r.abundancia, 999), 0, 999, '#6f7f5a', "Abundancia",
            "Abundancia total (N): número total de detecciones acumuladas. Refleja la actividad acústica del ecosistema.");

        // Fila superior: 3 gauges | Fila inferior: 2 gauges centrados
        const gaugesBioHTML = `
        <div class="gauges-grid">
            <div class="gauges-row-top">${g1}${g2}${g3}</div>
            <div class="gauges-row-bot">${g4}${g5}</div>
        </div>`;

        // ── Gauges entropía acústica — los 3 EN UNA SOLA FILA ────────────
        const ge1 = buildGaugeSVG(r.ht_avg ?? 0, 0, 1, '#326f72', "Ht",
            "Entropía temporal (Ht): mide cuánto varía la energía acústica en el tiempo. Valores altos = diversidad temporal de sonidos.");
        const ge2 = buildGaugeSVG(r.hf_avg ?? 0, 0, 1, '#405f82', "Hf",
            "Entropía espectral (Hf): distribución de energía entre bandas de frecuencia. Valores altos = uso espectral diverso.");
        const ge3 = buildGaugeSVG(r.h_avg ?? 0, 0, 1, '#2f6f4e', "H",
            "Entropía acústica compuesta (H = Ht × Hf): índice global de complejidad del paisaje sonoro. >0.6 = ecosistema sano.");

        const gaugesEntropyHTML = `
        <div class="gauges-entropy-row">${ge1}${ge2}${ge3}</div>`;

        //HTML completo 
        container.innerHTML = `
        <style>
            .sci-section-title {
                font-size:0.68rem; font-weight:700; letter-spacing:0.12em;
                text-transform:uppercase; color:#879389; margin-bottom:0.9rem;
                display:flex; align-items:center; gap:0.5rem;
            }
            .sci-section-title::before {
                content:''; display:inline-block; width:3px; height:14px;
                border-radius:2px; background:#2f6f4e;
            }
            /* ── GAUGE WRAPPER ── */
            .gauge-wrapper {
                display:flex; flex-direction:column; align-items:center;
                gap:0; cursor:help; transition:transform 0.15s;
            }
            .gauge-wrapper:hover { transform:none; }
            .gauge-label {
                font-size:0.7rem; font-weight:600; color:#5f6f65;
                margin:0; letter-spacing:0.05em; text-align:center;
            }

            /* ── LAYOUT 3+2 para biodiversidad ── */
            .gauges-grid { width:100%; }
            .gauges-row-top {
                display:flex; justify-content:space-around;
                flex-wrap:nowrap; margin-bottom:0.25rem;
            }
            .gauges-row-bot {
                display:flex; justify-content:center; gap:3rem;
            }

            /* ── FILA ÚNICA para entropías ── */
            .gauges-entropy-row {
                display:flex; justify-content:space-around;
                flex-wrap:nowrap; gap:0.5rem;
            }

            .science-composite-card { width:100%; }
            .science-card-body {
                display:flex; flex-direction:column; gap:1.05rem;
                height:100%; padding:1.25rem 1.45rem;
            }
            .science-card-head {
                display:flex; align-items:center; justify-content:space-between;
                gap:1rem; margin-bottom:0.1rem;
            }
            .science-card-head .sci-section-title { margin-bottom:0; }
            .science-panel-section { min-width:0; }
            .science-panel-divider {
                height:1px; width:100%; background:#dde3d8;
            }
            .science-chart-frame {
                height:260px; min-height:0; width:100%;
            }
            .soundscape-summary {
                display:flex; align-items:center; gap:1rem;
                min-width:0;
            }
            .soundscape-copy { min-width:0; }
            .soundscape-copy p {
                color:#5f6f65; font-size:0.82rem; line-height:1.4;
                margin:0;
            }

            /* ── BARRAS bioacústicas ── */
            .ndsi-badge { font-size:1.6rem; font-weight:800; line-height:1; }
            .index-bar-row {
                display:grid; grid-template-columns:90px 1fr 56px;
                align-items:center; gap:0.6rem; margin-bottom:0.55rem;
            }
            .index-bar-label { font-size:0.75rem; color:#5f6f65; font-weight:600; cursor:help; }
            .index-bar-track { height:8px; background:#dfe5db; border-radius:99px; overflow:hidden; }
            .index-bar-fill  { height:100%; border-radius:99px; transition:width 0.6s cubic-bezier(.4,0,.2,1); }
            .index-bar-val   { font-size:0.78rem; color:#1f2923; text-align:right; font-variant-numeric:tabular-nums; }
        </style>

        <!-- CABECERA -->
        <div class="d-flex justify-content-between align-items-start mb-4 animate-fade-in flex-wrap gap-2">
            <div>
                <h3 class="fw-bold text-white mb-1">
                    <i class="bi bi-binoculars-fill me-2 text-info"></i>Análisis Científico
                </h3>
                <p class="text-muted mb-0 small">
                    <i class="bi bi-geo-alt-fill me-1"></i>${r.zona || 'Zona desconocida'}
                    &nbsp;·&nbsp;<i class="bi bi-activity me-1"></i>${r.abundancia} detecciones
                    &nbsp;·&nbsp;<i class="bi bi-list-stars me-1"></i>${r.riqueza} especies únicas
                </p>
            </div>
            <div class="d-flex align-items-center gap-2 align-self-center">
                <button class="btn btn-success btn-sm" onclick="downloadScienceCSV()">
                    <i class="bi bi-filetype-csv me-2"></i>Exportar índices
                </button>
                <span class="badge bg-${calBadge} px-3 py-2 fs-6">
                    <i class="bi bi-stars me-1"></i>${calidadUpper}
                </span>
            </div>
        </div>

        <!-- Tarjetas compuestas: biodiversidad | paisaje sonoro -->
        <div class="row g-3 mb-3 animate-fade-in science-composite-row">

            <div class="col-xl-7 d-flex">
                <div class="card border-0 bg-dark science-composite-card">
                    <div class="card-body science-card-body">
                        <div class="science-card-head">
                            <p class="sci-section-title"><i class="bi bi-bar-chart-steps me-1"></i>Índices de Biodiversidad</p>
                        </div>

                        <div class="science-panel-section">
                            ${gaugesBioHTML}
                            <p class="text-muted mb-0" style="font-size:0.7rem;margin-top:0.5rem;">
                                <i class="bi bi-info-circle me-1"></i>Pasa el cursor sobre cada medidor para ver su definición.
                            </p>
                        </div>

                        <div class="science-panel-divider"></div>

                        <div class="science-panel-section">
                            <p class="sci-section-title"><i class="bi bi-bar-chart-fill me-1"></i>Comparativa de diversidad</p>
                            <div class="science-chart-frame">
                                <canvas id="scienceBarChart"></canvas>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="col-xl-5 d-flex">
                <div class="card border-0 bg-dark science-composite-card">
                    <div class="card-body science-card-body">
                        <div class="science-card-head">
                            <p class="sci-section-title"><i class="bi bi-soundwave me-1"></i>Paisaje Sonoro</p>
                        </div>

                        <div class="science-panel-section">
                            <p class="sci-section-title"><i class="bi bi-activity me-1"></i>NDSI</p>
                            <div class="soundscape-summary">
                                <div class="position-relative" style="width:56px;height:56px;flex-shrink:0;">
                                    <svg viewBox="0 0 56 56" width="56" height="56">
                                        <circle cx="28" cy="28" r="24" fill="none" stroke="#dfe5db" stroke-width="6"/>
                                        <circle cx="28" cy="28" r="24" fill="none"
                                            stroke="${(r.ndsi_avg ?? 0) >= 0 ? '#2f6f4e' : '#9c3f3f'}"
                                            stroke-width="6"
                                            stroke-dasharray="${Math.abs((r.ndsi_avg ?? 0)) * 75.4} 150.8"
                                            stroke-dashoffset="37.7"
                                            stroke-linecap="round"
                                            transform="rotate(-90 28 28)"/>
                                    </svg>
                                </div>
                                <div class="soundscape-copy">
                                    <div class="ndsi-badge" style="color:${(r.ndsi_avg ?? 0) >= 0 ? '#2f6f4e' : '#9c3f3f'};">
                                        ${(r.ndsi_avg ?? 0).toFixed(3)}
                                    </div>
                                    <p>
                                        ${(r.ndsi_avg ?? 0) > 0.5 ? 'Ambiente predominantemente natural' :
                (r.ndsi_avg ?? 0) > 0 ? 'Balance naturaleza / antropogénico' :
                    'Ruido antropogénico dominante'}
                                        <br><span class="text-white-50">Rango: −1 (urbano) → +1 (natural)</span>
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div class="science-panel-divider"></div>

                        <div class="science-panel-section">
                            <p class="sci-section-title"><i class="bi bi-waveform me-1"></i>Entropía Acústica</p>
                            ${gaugesEntropyHTML}
                        </div>

                        <div class="science-panel-divider"></div>

                        <div class="science-panel-section">
                            <p class="sci-section-title"><i class="bi bi-mic-fill me-1"></i>Índices Bioacústicos</p>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="Acoustic Complexity Index: variabilidad espectral de la grabación. Valores altos indican gran actividad biótica.">ACI</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.aci_avg ?? 0) / 2000 * 100, 100)}%;background:#405f82;"></div></div>
                                <span class="index-bar-val">${(r.aci_avg ?? 0).toFixed(1)}</span>
                            </div>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="Acoustic Diversity Index: diversidad de bandas de frecuencia ocupadas. Mayor ADI → mayor biodiversidad.">ADI</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.adi_avg ?? 0) / 3 * 100, 100)}%;background:#2f6f4e;"></div></div>
                                <span class="index-bar-val">${(r.adi_avg ?? 0).toFixed(3)}</span>
                            </div>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="Acoustic Evenness Index: uniformidad del uso espectral. Valores bajos indican mayor riqueza sonora.">AEI</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.aei_avg ?? 0) * 100, 100)}%;background:#a66f2f;"></div></div>
                                <span class="index-bar-val">${(r.aei_avg ?? 0).toFixed(3)}</span>
                            </div>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="Bioacoustic Index: energía acústica en la banda de biofonia (2–8 kHz). Indica intensidad de la actividad biológica.">BIO</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.bio_avg ?? 0) / 100 * 100, 100)}%;background:#6f7f5a;"></div></div>
                                <span class="index-bar-val">${(r.bio_avg ?? 0).toFixed(2)}</span>
                            </div>
                            <p class="text-muted mt-2 mb-0" style="font-size:0.68rem;">
                                <i class="bi bi-info-circle me-1"></i>Media agregada de las muestras acústicas registradas.
                            </p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- FILA 3: Mapa -->
        <div class="row g-3 animate-fade-in" style="min-height:340px;">
            <div class="col-12 d-flex flex-column">
                <div class="card border-0 bg-dark flex-grow-1 d-flex flex-column">
                    <div class="card-body p-0 d-flex flex-column">
                        <div class="px-4 pt-3 pb-2">
                            <p class="sci-section-title mb-0">
                                <i class="bi bi-map-fill me-1"></i>Cobertura Geoespacial del Nodo
                            </p>
                        </div>
                        <div id="biodiversityMap" style="flex:1;min-height:280px;border-bottom-left-radius:8px;border-bottom-right-radius:8px;"></div>
                    </div>
                </div>
            </div>
        </div>`;

        // Chart.js barras 
        const barCtx = document.getElementById('scienceBarChart');
        if (barCtx) {
            new Chart(barCtx.getContext('2d'), {
                type: 'bar',
                data: {
                    labels: ["Shannon (H')", 'Simpson (1-D)', "Pielou (J')", 'Riqueza (norm.)', 'Entropía (H)'],
                    datasets: [{
                        label: 'Valor',
                        data: [
                            r.shannon,
                            r.simpson,
                            r.pielou,
                            parseFloat((r.riqueza / 30).toFixed(3)),
                            r.h_avg ?? 0
                        ],
                        backgroundColor: [
                            'rgba(64,95,130,0.82)', 'rgba(50,111,114,0.82)',
                            'rgba(47,111,78,0.82)', 'rgba(166,111,47,0.82)',
                            'rgba(111,127,90,0.82)'
                        ],
                        borderColor: ['#405f82', '#326f72', '#2f6f4e', '#a66f2f', '#6f7f5a'],
                        borderWidth: 1.5, borderRadius: 6,
                    }]
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                afterLabel: ctx => {
                                    const tips = [
                                        'Rango típico: 0–5  |  >3 Excelente',
                                        'Rango: 0–1  |  >0.7 Alta diversidad',
                                        'Rango: 0–1  |  1 = Equitabilidad máxima',
                                        'Riqueza / 30 (escala visual)',
                                        'H = Ht × Hf  |  >0.6 Ecosistema sano',
                                    ];
                                    return tips[ctx.dataIndex] || '';
                                }
                            }
                        }
                    },
                    scales: {
                        y: { min: 0, max: 5, grid: { color: '#dde3d8' }, ticks: { color: '#5f6f65', font: { size: 11 } } },
                        x: { grid: { display: false }, ticks: { color: '#5f6f65', font: { size: 12 } } }
                    }
                }
            });
        }

        //Mapa Leaflet
        fetch("http://100.98.248.58:8000/analytics/map")
            .then(res => res.json())
            .then(mapData => {
                if (mapData.error) return;
                const map = L.map('biodiversityMap').setView([mapData.lat, mapData.lon], 13);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; OpenStreetMap'
                }).addTo(map);
                const marker = L.marker([mapData.lat, mapData.lon]).addTo(map);
                marker.bindPopup(`<b>${mapData.ciudad}</b><br>Biodiversidad H': <b>${mapData.shannon}</b>`).openPopup();
                const circleColor = mapData.shannon > 1.5 ? '#2f6f4e' : '#9c3f3f';
                L.circle([mapData.lat, mapData.lon], {
                    color: circleColor, fillColor: circleColor,
                    fillOpacity: 0.15, radius: mapData.radio_km * 1000
                }).addTo(map);
            })
            .catch(() => { });

    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger mt-4">Error al cargar el análisis: ${e.message}</div>`;
    }
}

function downloadScienceCSV() {
    if (!currentScienceReport || currentScienceReport.length === 0) {
        alert("No hay índices ecológicos para exportar");
        return;
    }

    const rows = currentScienceReport.map(r => [
        r.zona || 'Zona desconocida',
        r.calidad || '',
        r.abundancia ?? 0,
        r.riqueza ?? 0,
        r.shannon ?? 0,
        r.simpson ?? 0,
        r.pielou ?? 0,
        r.rms_avg ?? '',
        r.aci_avg ?? 0,
        r.adi_avg ?? 0,
        r.aei_avg ?? 0,
        r.bio_avg ?? 0,
        r.ndsi_avg ?? 0,
        r.ht_avg ?? 0,
        r.hf_avg ?? 0,
        r.h_avg ?? 0
    ]);

    downloadTableCSV(
        `birdmonitor_indices_${new Date().toISOString().slice(0, 10)}.csv`,
        [
            'Zona',
            'Calidad_Shannon',
            'Abundancia_N',
            'Riqueza_S',
            'Shannon_H',
            'Simpson_1-D',
            'Pielou_J',
            'RMS_Medio',
            'ACI_Medio',
            'ADI_Medio',
            'AEI_Medio',
            'BIO_Medio',
            'NDSI_Medio',
            'Entropia_Temporal_Ht',
            'Entropia_Frecuencial_Hf',
            'Entropia_Acustica_H'
        ],
        rows
    );
}

//NODOS
async function renderNodesView(container) {
    container.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-success"></div></div>`;
    try {
        const res = await fetch(API_URL.replace('detections/', 'devices/'));
        const nodos = await res.json();

        let nodesHtml = '';
        nodos.forEach(node => {
            nodesHtml += `
            <div class="col-md-4 mb-4">
                <div class="card bg-dark text-white border-0 shadow-sm node-card h-100">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h5 class="fw-bold m-0"><i class="bi bi-cpu text-info me-2"></i>${node.name}</h5>
                            <span class="badge bg-success animate-pulse">ONLINE</span>
                        </div>
                        <p class="text-muted small mb-1"><i class="bi bi-geo-alt me-1"></i> ${node.location}</p>
                        <p class="text-muted small mb-3"><i class="bi bi-record-circle me-1"></i> ID BDD: <span class="font-monospace">${node.id}</span></p>
                    </div>
                </div>
            </div>`;
        });

        container.innerHTML = `
            <div class="row mb-4 animate-fade-in">
                <div class="col-12">
                    <h3 class="fw-bold text-white"><i class="bi bi-router me-2 text-accent"></i>Red de Nodos (ARUs)</h3>
                </div>
            </div>
            <div class="row animate-fade-in">${nodesHtml}</div>`;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Error cargando nodos: ${e.message}</div>`;
    }
}

//VISTA INFORME DIARIO 
let dailyChartInst = null;
let currentDailyData = [];

async function renderDailyView(container) {
    // Obtenemos la fecha actual en formato YYYY-MM-DD
    const today = new Date().toISOString().split('T')[0];

    container.innerHTML = `
        <div class="row mb-4 animate-fade-in">
            <div class="col-12 d-flex justify-content-between align-items-center flex-wrap gap-3">
                <div>
                    <h3 class="fw-bold text-white"><i class="bi bi-calendar2-range-fill text-accent me-2"></i>Informe Diario</h3>
                    <p class="text-muted mb-0">Densidad de actividad acústica biológica por hora</p>
                </div>
                <div class="d-flex gap-2 align-items-center">
                    <input type="date" id="daily-date-picker" class="form-control bg-dark text-white border-secondary" value="${today}">
                    <button class="btn btn-success d-flex align-items-center" onclick="downloadDailyCSV()">
                        <i class="bi bi-filetype-csv me-2"></i>Exportar tabla
                    </button>
                </div>
            </div>
        </div>
        <div class="row mb-4 animate-fade-in">
            <div class="col-12">
                <div class="card shadow-sm border-0 bg-dark">
                    <div class="card-body">
                        <h6 class="text-uppercase fw-bold text-muted mb-3"><i class="bi bi-bar-chart-fill me-2"></i>Curva de Actividad Avifauna</h6>
                        <div style="height: 320px;"><canvas id="dailyChart"></canvas></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="row animate-fade-in">
            <div class="col-12">
                <div class="card shadow-sm border-0 bg-dark overflow-hidden">
                    <div class="table-responsive">
                        <table class="table table-dark table-hover mb-0 align-middle">
                            <thead class="bg-dark-subtle text-uppercase small">
                                <tr>
                                    <th class="ps-4 py-3">Eje X · Tramo Horario</th>
                                    <th class="py-3">Eje Y · Cantos</th>
                                    <th class="py-3">Confianza Media</th>
                                    <th class="py-3">Especies Activas</th>
                                    <th class="pe-4 py-3">Taxones Identificados</th>
                                </tr>
                            </thead>
                            <tbody id="daily-table-body"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    `;

    // Escuchamos los cambios en el calendario para actualizar al instante
    document.getElementById('daily-date-picker').addEventListener('change', (e) => loadDailyData(e.target.value));

    // Cargamos los datos del día por defecto
    loadDailyData(today);
}

async function loadDailyData(dateStr) {
    try {
        const res = await fetch(`http://100.98.248.58:8000/analytics/daily-activity?date=${dateStr}`);
        const data = await res.json();
        currentDailyData = data;

        // 1. DIBUJAR GRÁFICO (Chart.js)
        const ctx = document.getElementById('dailyChart');
        if (dailyChartInst) dailyChartInst.destroy();

        const labels = data.map(d => `${String(d.hora).padStart(2, '0')}:00`);
        const counts = data.map(d => d.total_detecciones);

        dailyChartInst = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Registros válidos',
                    data: counts,
                    backgroundColor: 'rgba(47, 111, 78, 0.82)',
                    borderColor: '#22543a',
                    borderWidth: 1,
                    borderRadius: 4
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    y: { beginAtZero: true, grid: { color: '#dde3d8' }, ticks: { color: '#5f6f65' } },
                    x: { grid: { display: false }, ticks: { color: '#5f6f65' } }
                },
                plugins: { legend: { display: false } }
            }
        });

        // 2. RELLENAR TABLA
        const tbody = document.getElementById('daily-table-body');
        tbody.innerHTML = data.map(d => `
            <tr>
                <td class="ps-4 text-white-50 font-monospace">${String(d.hora).padStart(2, '0')}:00 - ${String(d.hora).padStart(2, '0')}:59</td>
                <td><span class="badge bg-${d.total_detecciones > 0 ? 'success' : 'secondary'} fs-6">${d.total_detecciones}</span></td>
                <td><span class="text-white-50">${Number(d.confianza_media || 0).toFixed(3)}</span></td>
                <td><span class="text-white fw-bold">${d.especies_activas}</span></td>
                <td class="pe-4 text-muted small">${d.lista_especies.join(', ') || '-'}</td>
            </tr>
        `).join('');

    } catch (e) {
        console.error("Error cargando informe diario:", e);
    }
}

function downloadDailyCSV() {
    if (!currentDailyData || currentDailyData.length === 0) return;

    const date = document.getElementById('daily-date-picker').value;

    const rows = currentDailyData.map(d => {
        const hora = String(d.hora).padStart(2, '0');
        return [
            date,
            `${hora}:00`,
            `${hora}:00 - ${hora}:59`,
            d.total_detecciones,
            d.confianza_media ?? 0,
            d.especies_activas,
            d.lista_especies || []
        ];
    });

    downloadTableCSV(
        `birdmonitor_actividad_horaria_${date}.csv`,
        [
            'Fecha',
            'Eje_X_Hora',
            'Tramo_Horario',
            'Eje_Y_Cantos_Total_Detecciones',
            'Confianza_Media',
            'Especies_Activas',
            'Taxones_Identificados'
        ],
        rows
    );
}

//ARRANQUE
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('main-content');
    if (container) { container.className = "d-flex flex-column flex-grow-1 w-100"; container.innerHTML = getDashboardHTML(); }
    switchView('dashboard');
    setInterval(updateDashboard, 4000);

    // pal responsive del movil
    const menuToggle = document.getElementById('mobile-menu-toggle');
    const sidebar = document.getElementById('sidebar-wrapper');

    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay d-md-none';
    document.body.appendChild(overlay);

    function toggleMenu() {
        sidebar.classList.toggle('show-mobile');
        overlay.classList.toggle('show');
    }

    if (menuToggle) menuToggle.addEventListener('click', toggleMenu);
    overlay.addEventListener('click', toggleMenu);

    document.querySelectorAll('.sidebar-nav .nav-link').forEach(link => {
        link.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.remove('show-mobile');
                overlay.classList.remove('show');
            }
        });
    });
});