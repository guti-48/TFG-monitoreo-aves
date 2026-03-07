const API_URL = "http://127.0.0.1:8000/detections/";
const IMG_BASE_URL = "http://127.0.0.1:8000/spectrograms/";

const ASSETS_PATH = 'assets/'; 
const NOISE_MAP = {
    'Human vocal': 'human.png',
    'Motor': 'ruido_amb.png', 
};
const PLACEHOLDER_IMG = ASSETS_PATH + 'placeholder.jpg';

let currentView = 'dashboard'; 
let activeNodeFilter = null;
let myChart = null;
let intervalId = null;

const MOCK_NODES = [
    { id: 'RaspberryPi_01',      name: 'Nodo Algeciras', location: 'Cádiz, ES',    status: 'online',  lat: 37.38, lon: -5.97, ip: '192.168.1.35' },
    { id: 'RaspberryPi_Sanguesa',name: 'Nodo Sangüesa',  location: 'Navarra, ES',  status: 'offline', lat: 42.57, lon: -1.28, ip: '10.0.0.5' },
    { id: 'RaspberryPi_Madrid',  name: 'Nodo Bilbao',    location: 'Bilbao, EH',   status: 'offline', lat: 40.41, lon: -3.70, ip: '192.168.0.10' }
];

// ════════════════════════════════════════════════════════════════
// NAVEGACIÓN
// ════════════════════════════════════════════════════════════════

function switchView(viewName, nodeFilter = null) {
    currentView    = viewName;
    activeNodeFilter = nodeFilter;

    ['btn-dashboard','btn-nodes','btn-history','btn-science'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.className = 'nav-link';
    });

    const map = { dashboard:'btn-dashboard', history:'btn-history', nodes:'btn-nodes', science:'btn-science' };
    const active = document.getElementById(map[viewName]);
    if (active) active.className = 'nav-link active';

    const container = document.getElementById('main-content');
    if (!container) return;

    container.className = 'd-flex flex-column flex-grow-1 w-100';
    if (viewName === 'history') container.classList.add('view-history');

    if      (viewName === 'dashboard') { container.innerHTML = getDashboardHTML(); updateDashboard(); }
    else if (viewName === 'history')    renderHistoryView(container);
    else if (viewName === 'nodes')      renderNodesView(container);
    else if (viewName === 'science')    renderScienceView(container);
}

// ════════════════════════════════════════════════════════════════
// HISTÓRICO
// ════════════════════════════════════════════════════════════════

async function renderHistoryView(container) {
    container.innerHTML = `<div class="d-flex justify-content-center align-items-center py-5"><div class="spinner-border text-success" role="status"></div><span class="ms-3 text-muted">Cargando base de datos completa...</span></div>`;
    try {
        const response   = await fetch(`${API_URL}?limit=500`);
        const data       = await response.json();
        const sortedData = data.reverse(); 
        let rowsHtml = '';
        sortedData.forEach(d => {
            const timeDate = new Date(d.timestamp);
            const dateStr  = timeDate.toLocaleDateString();
            const timeStr  = timeDate.toLocaleTimeString();
            const imgUrl   = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
            const clean    = cleanName(d.species);
            let icon = '<i class="bi bi-music-note-beamed text-success"></i>';
            if (d.species.includes("Human") || d.species.includes("Motor") || d.species.includes("Noise"))
                icon = '<i class="bi bi-boombox text-warning"></i>';
            rowsHtml += `
            <tr>
                <td class="text-white-50 small">${d.id}</td>
                <td>${dateStr} <small class="text-muted">${timeStr}</small></td>
                <td><div class="d-flex align-items-center"><div class="me-2">${icon}</div><span class="fw-bold text-white">${clean}</span></div></td>
                <td>${d.device_name || 'RaspberryPi'}</td>
                <td><div class="progress" style="height:6px;width:100px;"><div class="progress-bar bg-${d.confidence > 0.8 ? 'success' : 'warning'}" role="progressbar" style="width:${d.confidence*100}%"></div></div></td>
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

// ════════════════════════════════════════════════════════════════
// DASHBOARD TIEMPO REAL
// ════════════════════════════════════════════════════════════════

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
        if (avgAmp > 30) { noiseLabel = "Ruidoso";  noiseColor = "danger";  noiseIcon = "bi-speaker-fill"; }

        const noiseEl = document.getElementById('noise-metric');
        if (noiseEl) {
            noiseEl.innerText = `${noiseLabel} (Vol: ${avgAmp.toFixed(0)})`;
            noiseEl.className = `fw-bold mb-0 fs-5 text-${noiseColor}`;
            document.getElementById('noise-card').className     = `card kpi-card border-start-${noiseColor}`;
            document.getElementById('noise-icon-box').className = `icon-box bg-${noiseColor}-subtle text-${noiseColor}`;
            document.getElementById('noise-icon').className     = `bi ${noiseIcon} fs-3`;
        }

        const birdsOnly = sortedData.filter(d =>
            !d.species.toLowerCase().includes("noise") &&
            !d.species.toLowerCase().includes("ruido") &&
            !d.species.toLowerCase().includes("ambiente")
        );
        safeSetText('total-counter', birdsOnly.length); 

        if (birdsOnly.length > 0) {
            const latestBird = birdsOnly[0]; 
            safeSetText('last-activity', new Date(latestBird.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}));
            const counts = {};
            birdsOnly.forEach(d => { counts[d.species] = (counts[d.species] || 0) + 1; });
            const topSpecies = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
            safeSetText('top-species', cleanName(topSpecies));
            if (typeof renderLiveFeedSplit === "function") await renderLiveFeedSplit(latestBird);
            if (typeof renderTable         === "function") renderTable(birdsOnly.slice(0, 10));
            if (typeof updateChart         === "function") updateChart(counts);
        }
    } catch (error) { console.error("Error Dashboard:", error); }
}

function getDashboardHTML() {
    return `
    <h4 class="mb-4 fw-bold" id="dashboard-title">Monitorización Global</h4>
    <div class="row g-4 mb-4">
        <div class="col-md-3"><div class="card kpi-card border-start-success"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Detecciones Totales</p><h3 class="fw-bold mb-0" id="total-counter">0</h3></div><div class="icon-box bg-success-subtle text-success"><i class="bi bi-soundwave fs-3"></i></div></div></div></div>
        <div class="col-md-3"><div class="card kpi-card border-start-earth"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Especie Dominante</p><h4 class="fw-bold mb-0 fs-5 text-truncate" id="top-species">-</h4></div><div class="icon-box bg-earth-subtle text-earth"><i class="bi bi-trophy-fill fs-3"></i></div></div></div></div>
        <div class="col-md-3"><div class="card kpi-card border-start-info"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Última Actividad</p><h4 class="fw-bold mb-0 fs-5" id="last-activity">--:--</h4></div><div class="icon-box bg-info-subtle text-info"><i class="bi bi-clock-history fs-3"></i></div></div></div></div>
        <div class="col-md-3"><div class="card kpi-card border-start-secondary" id="noise-card"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Nivel de Ruido</p><h4 class="fw-bold mb-0 fs-5" id="noise-metric">Calculando...</h4></div><div class="icon-box bg-secondary-subtle" id="noise-icon-box"><i class="bi bi-boombox fs-3" id="noise-icon"></i></div></div></div></div>
    </div>
    <div class="row g-4 mb-5">
        <div class="col-lg-7"><div class="card shadow-sm border-0 bg-dark overflow-hidden" style="min-height:420px;"><div class="card-body p-0 d-flex flex-column h-100" id="live-feed-container"><div class="d-flex align-items-center justify-content-center flex-grow-1 text-muted"><p>Esperando datos...</p></div></div></div></div>
        <div class="col-lg-5"><div class="card h-100 shadow-sm border-0"><div class="card-header bg-transparent border-0 py-3"><h5 class="fw-bold m-0">Distribución de Especies</h5></div><div class="card-body"><canvas id="speciesChart" style="max-height:300px;"></canvas></div></div></div>
    </div>
    <div class="row"><div class="col-12"><div class="card shadow-sm border-0 bg-dark"><div class="card-header bg-transparent border-0 py-3"><h5 class="fw-bold text-white m-0">Registro Reciente</h5></div><div class="table-responsive"><table class="table table-dark table-hover align-middle mb-0"><thead class="bg-dark-subtle text-uppercase small"><tr><th class="ps-4">Hora</th><th>Especie</th><th>Confianza</th><th>Espectrograma</th><th class="text-end pe-4">ID</th></tr></thead><tbody id="history-table-body"></tbody></table></div></div></div></div>`;
}

async function downloadCSV() {
    try {
        const response = await fetch(`${API_URL}?limit=1000`);
        const data = await response.json();
        if (!data || data.length === 0) { alert("Sin datos"); return; }
        let csvContent = "data:text/csv;charset=utf-8,ID,Fecha,Hora,Especie,Confianza,Nodo,Archivo\n";
        data.forEach(row => {
            const dateObj = new Date(row.timestamp);
            const especie = cleanName(row.species).replace(/,/g, ''); 
            csvContent += `${row.id},${dateObj.toLocaleDateString()},${dateObj.toLocaleTimeString()},${especie},${row.confidence},${row.device_name},${row.filename}\n`;
        });
        const encodedUri = encodeURI(csvContent);
        const link = document.createElement("a");
        link.setAttribute("href", encodedUri);
        link.setAttribute("download", `birdmonitor_${new Date().toISOString().slice(0,10)}.csv`);
        document.body.appendChild(link); link.click(); document.body.removeChild(link);
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
        const res    = await fetch(wikiUrl);
        const data   = await res.json();
        const pages  = data.query.pages;
        const pageId = Object.keys(pages)[0];
        if (pageId !== "-1" && pages[pageId].thumbnail) return pages[pageId].thumbnail.source;
    } catch (e) { console.error("Error Wiki", e); }
    return PLACEHOLDER_IMG;
}

async function renderLiveFeedSplit(d) {
    const container = document.getElementById('live-feed-container');
    if (!container) return;
    const species         = cleanName(d.species);
    const percent         = (d.confidence * 100).toFixed(0);
    const spectrogramUrl  = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
    const timeStr         = new Date(d.timestamp).toLocaleTimeString();
    const speciesPhotoUrl = await getSpeciesImageUrl(d.species);

    container.innerHTML = `
        <div class="main-detection-split w-100">
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
        const clean  = cleanName(d.species);
        let icon = '<i class="bi bi-feather text-success me-2"></i>';
        if (NOISE_MAP[clean] || d.species.includes("Human") || d.species.includes("Motor"))
            icon = '<i class="bi bi-boombox text-muted me-2"></i>';
        tbody.innerHTML += `<tr><td class="ps-4 fw-bold text-muted">${new Date(d.timestamp).toLocaleTimeString()}</td><td><div class="d-flex align-items-center">${icon}<span class="fw-semibold text-white">${clean}</span></div></td><td><span class="badge bg-dark-subtle text-success border">${(d.confidence*100).toFixed(0)}%</span></td><td><a href="${imgUrl}" target="_blank"><img src="${imgUrl}" class="table-img-preview" onerror="this.style.display='none'"></a></td><td class="text-end pe-4 text-muted small">#${d.id}</td></tr>`;
    });
}

function updateChart(counts) {
    const canvas = document.getElementById('speciesChart');
    if (!canvas) return;
    if (myChart) { myChart.destroy(); }
    const ctx    = canvas.getContext('2d');
    const labels = Object.keys(counts).map(cleanName);
    const values = Object.values(counts);
    const natureColors = ['#2E7D32','#C49A6C','#0288D1','#689F38','#8D6E63'];
    myChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: natureColors, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#e0e0e0' } } } }
    });
}

function safeSetText(id, text) { const el = document.getElementById(id); if (el) el.innerText = text; }
function cleanName(name) { if (!name) return "Desconocido"; let cleaned = name.split('_')[1] || name; return cleaned.charAt(0).toUpperCase() + cleaned.slice(1); }


// ════════════════════════════════════════════════════════════════
// TOOLTIP CUSTOM — se monta una sola vez en el body
// Soluciona el problema de title="" que no funciona sobre SVG
// ════════════════════════════════════════════════════════════════

(function mountTooltip() {
    const tt = document.createElement('div');
    tt.id = 'gauge-tooltip';
    tt.style.cssText = `
        position:fixed; z-index:9999; pointer-events:none;
        background:#0f1412; color:#e2e8e2; border:1px solid #2a3530;
        border-radius:8px; padding:8px 12px; font-size:0.75rem;
        max-width:260px; line-height:1.5; box-shadow:0 4px 20px #00000080;
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
        if (x + 270 > window.innerWidth)  x = e.clientX - 274;
        if (y + 100 > window.innerHeight) y = e.clientY - 80;
        tt.style.left = x + 'px';
        tt.style.top  = y + 'px';
    });
    document.addEventListener('mouseout', e => {
        if (!e.target.closest('[data-gauge-tip]')) return;
        const to = e.relatedTarget;
        if (to && to.closest('[data-gauge-tip]') === e.target.closest('[data-gauge-tip]')) return;
        tt.style.opacity = '0';
    });
})();


// ════════════════════════════════════════════════════════════════
// GAUGE SVG
// Usa data-gauge-tip en lugar de title="" para el tooltip custom
// ════════════════════════════════════════════════════════════════

function buildGaugeSVG(value, min, max, color, label, tooltip) {
    const R  = 52;
    const CX = 70, CY = 70;
    const startAngle = -210;
    const sweepTotal = 240;

    const clampedVal  = Math.min(Math.max(value, min), max);
    const pct         = (clampedVal - min) / (max - min);
    const sweepActive = sweepTotal * pct;

    function polarToXY(angleDeg, r) {
        const rad = (angleDeg - 90) * (Math.PI / 180);
        return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
    }
    function arcPath(fromDeg, toDeg, r) {
        const p1    = polarToXY(fromDeg, r);
        const p2    = polarToXY(toDeg, r);
        const large = (toDeg - fromDeg) > 180 ? 1 : 0;
        return `M ${p1.x} ${p1.y} A ${r} ${r} 0 ${large} 1 ${p2.x} ${p2.y}`;
    }

    const endAngle   = startAngle + sweepTotal;
    const activeEnd  = startAngle + sweepActive;
    const displayVal = (value % 1 === 0) ? value.toFixed(0) : value.toFixed(3);
    const textColor  = pct >= 0.65 ? '#4ade80' : pct >= 0.35 ? '#fbbf24' : '#f87171';
    // Escapamos las comillas del tooltip para el atributo HTML
    const tipEscaped = tooltip.replace(/"/g, '&quot;');

    return `
    <div class="gauge-wrapper" data-gauge-tip="${tipEscaped}">
        <svg viewBox="0 0 140 100" width="140" height="100" xmlns="http://www.w3.org/2000/svg" style="pointer-events:none;">
            <path d="${arcPath(startAngle, endAngle, R)}"
                  fill="none" stroke="#2a2e2c" stroke-width="10" stroke-linecap="round"/>
            <path d="${arcPath(startAngle, activeEnd, R)}"
                  fill="none" stroke="${color}" stroke-width="10" stroke-linecap="round"
                  style="filter:drop-shadow(0 0 4px ${color}80);"/>
            <text x="${CX}" y="${CY - 4}" text-anchor="middle"
                  font-size="18" font-weight="700" fill="${textColor}" font-family="DM Sans,sans-serif">
                ${displayVal}
            </text>
            <text x="${CX}" y="${CY + 13}" text-anchor="middle"
                  font-size="9" fill="#6b7280" font-family="DM Sans,sans-serif" letter-spacing="1">
                ${label.toUpperCase()}
            </text>
            <text x="20"  y="92" text-anchor="middle" font-size="8" fill="#4b5563">${min}</text>
            <text x="120" y="92" text-anchor="middle" font-size="8" fill="#4b5563">${max % 1 === 0 ? max : max.toFixed(1)}</text>
        </svg>
        <p class="gauge-label">${label}</p>
    </div>`;
}


// ════════════════════════════════════════════════════════════════
// VISTA ANÁLISIS ECO
// ════════════════════════════════════════════════════════════════

async function renderScienceView(container) {
    container.innerHTML = `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="spinner-grow text-info" role="status"></div>
            <span class="ms-3 text-white">Procesando datos del nodo...</span>
        </div>`;
    try {
        const response = await fetch("http://127.0.0.1:8000/analytics/biodiversity");
        const report   = await response.json();
        if (!report || report.length === 0) {
            container.innerHTML = `<div class="alert alert-warning text-center mt-4">Esperando detecciones reales del nodo...</div>`;
            return;
        }

        const r = report[0];

        const calidad      = r.calidad || 'POBRE';
        const calidadUpper = calidad.toUpperCase();
        const calBadge     = calidadUpper === 'EXCELENTE' ? 'success' : calidadUpper === 'MODERADO' ? 'warning' : 'danger';

        // ── Gauges biodiversidad — LAYOUT 3+2 ────────────────────────────
        // Usamos flex-wrap + flex-basis 33%/50% para forzar la rejilla
        const g1 = buildGaugeSVG(r.shannon, 0, 5, '#60a5fa', "Shannon H'",
            "Índice de Shannon-Wiener (H'): mide diversidad considerando riqueza y equitabilidad. >3 = Excelente, 1.5–3 = Moderado, <1.5 = Pobre.");
        const g2 = buildGaugeSVG(r.simpson, 0, 1, '#a78bfa', "Simpson 1-D",
            "Índice de Simpson (1-D): probabilidad de que dos individuos elegidos al azar pertenezcan a especies distintas. Próximo a 1 = alta diversidad.");
        const g3 = buildGaugeSVG(r.pielou,  0, 1, '#34d399', "Pielou J'",
            "Índice de equitabilidad de Pielou (J'): uniformidad en la distribución de individuos entre especies. 1 = perfectamente equitativo.");
        const g4 = buildGaugeSVG(Math.min(r.riqueza, 30),      0, 30,  '#f59e0b', "Riqueza S",
            "Riqueza específica (S): número de especies únicas detectadas. Indicador primario de biodiversidad.");
        const g5 = buildGaugeSVG(Math.min(r.abundancia, 999),  0, 999, '#fb923c', "Abundancia",
            "Abundancia total (N): número total de detecciones acumuladas. Refleja la actividad acústica del ecosistema.");

        // Fila superior: 3 gauges | Fila inferior: 2 gauges centrados
        const gaugesBioHTML = `
        <div class="gauges-grid">
            <div class="gauges-row-top">${g1}${g2}${g3}</div>
            <div class="gauges-row-bot">${g4}${g5}</div>
        </div>`;

        // ── Gauges entropía acústica — los 3 EN UNA SOLA FILA ────────────
        const ge1 = buildGaugeSVG(r.ht_avg ?? 0, 0, 1, '#38bdf8', "Ht",
            "Entropía temporal (Ht): mide cuánto varía la energía acústica en el tiempo. Valores altos = diversidad temporal de sonidos.");
        const ge2 = buildGaugeSVG(r.hf_avg ?? 0, 0, 1, '#818cf8', "Hf",
            "Entropía espectral (Hf): distribución de energía entre bandas de frecuencia. Valores altos = uso espectral diverso.");
        const ge3 = buildGaugeSVG(r.h_avg  ?? 0, 0, 1, '#e879f9', "H",
            "Entropía acústica compuesta (H = Ht × Hf): índice global de complejidad del paisaje sonoro. >0.6 = ecosistema sano.");

        const gaugesEntropyHTML = `
        <div class="gauges-entropy-row">${ge1}${ge2}${ge3}</div>`;

        // ── HTML completo ─────────────────────────────────────────────────
        container.innerHTML = `
        <style>
            .sci-section-title {
                font-size:0.68rem; font-weight:700; letter-spacing:0.12em;
                text-transform:uppercase; color:#6b7280; margin-bottom:0.9rem;
                display:flex; align-items:center; gap:0.5rem;
            }
            .sci-section-title::before {
                content:''; display:inline-block; width:3px; height:14px;
                border-radius:2px; background:#38b261;
            }
            /* ── GAUGE WRAPPER ── */
            .gauge-wrapper {
                display:flex; flex-direction:column; align-items:center;
                gap:0; cursor:help; transition:transform 0.15s;
            }
            .gauge-wrapper:hover { transform:scale(1.06); }
            .gauge-label {
                font-size:0.7rem; font-weight:600; color:#9ca3af;
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

            /* ── BARRAS bioacústicas ── */
            .ndsi-badge { font-size:1.6rem; font-weight:800; line-height:1; }
            .index-bar-row {
                display:grid; grid-template-columns:90px 1fr 56px;
                align-items:center; gap:0.6rem; margin-bottom:0.55rem;
            }
            .index-bar-label { font-size:0.75rem; color:#9ca3af; font-weight:600; cursor:help; }
            .index-bar-track { height:8px; background:#1f2421; border-radius:99px; overflow:hidden; }
            .index-bar-fill  { height:100%; border-radius:99px; transition:width 0.6s cubic-bezier(.4,0,.2,1); }
            .index-bar-val   { font-size:0.78rem; color:#e5e7eb; text-align:right; font-variant-numeric:tabular-nums; }
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
            <span class="badge bg-${calBadge} px-3 py-2 fs-6 align-self-center">
                <i class="bi bi-stars me-1"></i>${calidadUpper}
            </span>
        </div>

        <!-- FILA 1: Gauges biodiversidad (3+2) | NDSI + entropías (3 en fila) -->
        <div class="row g-3 mb-3 animate-fade-in">

            <div class="col-lg-7">
                <div class="card border-0 bg-dark h-100">
                    <div class="card-body">
                        <p class="sci-section-title"><i class="bi bi-bar-chart-steps me-1"></i>Índices de Biodiversidad</p>
                        ${gaugesBioHTML}
                        <p class="text-muted mb-0" style="font-size:0.7rem;margin-top:0.5rem;">
                            <i class="bi bi-info-circle me-1"></i>Pasa el cursor sobre cada medidor para ver su definición.
                        </p>
                    </div>
                </div>
            </div>

            <div class="col-lg-5">
                <div class="card border-0 bg-dark h-100">
                    <div class="card-body d-flex flex-column gap-3">

                        <!-- NDSI -->
                        <div>
                            <p class="sci-section-title"><i class="bi bi-soundwave me-1"></i>Paisaje Sonoro (NDSI)</p>
                            <div class="d-flex align-items-center gap-3">
                                <div class="position-relative" style="width:56px;height:56px;flex-shrink:0;">
                                    <svg viewBox="0 0 56 56" width="56" height="56">
                                        <circle cx="28" cy="28" r="24" fill="none" stroke="#1f2421" stroke-width="6"/>
                                        <circle cx="28" cy="28" r="24" fill="none"
                                            stroke="${(r.ndsi_avg ?? 0) >= 0 ? '#4ade80' : '#f87171'}"
                                            stroke-width="6"
                                            stroke-dasharray="${Math.abs((r.ndsi_avg ?? 0)) * 75.4} 150.8"
                                            stroke-dashoffset="37.7"
                                            stroke-linecap="round"
                                            style="filter:drop-shadow(0 0 5px ${(r.ndsi_avg ?? 0) >= 0 ? '#4ade8060' : '#f8717160'});"
                                            transform="rotate(-90 28 28)"/>
                                    </svg>
                                </div>
                                <div>
                                    <div class="ndsi-badge" style="color:${(r.ndsi_avg ?? 0) >= 0 ? '#4ade80' : '#f87171'};">
                                        ${(r.ndsi_avg ?? 0).toFixed(3)}
                                    </div>
                                    <div class="text-muted" style="font-size:0.72rem;line-height:1.3;">
                                        ${(r.ndsi_avg ?? 0) > 0.5 ? '🌿 Ambiente predominantemente natural' :
                                          (r.ndsi_avg ?? 0) > 0   ? '⚖️ Balance naturaleza / antropogénico' :
                                                                     '🏙️ Ruido antropogénico dominante'}
                                        <br><span class="text-white-50">Rango: −1 (urbano) → +1 (natural)</span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Entropías acústicas — 3 en una fila -->
                        <div>
                            <p class="sci-section-title"><i class="bi bi-waveform me-1"></i>Entropía Acústica</p>
                            ${gaugesEntropyHTML}
                        </div>

                    </div>
                </div>
            </div>
        </div>

        <!-- FILA 2: Barras bioacústicas | Gráfico barras diversidad -->
        <div class="row g-3 mb-3 animate-fade-in">

            <div class="col-lg-5">
                <div class="card border-0 bg-dark h-100">
                    <div class="card-body">
                        <p class="sci-section-title"><i class="bi bi-mic-fill me-1"></i>Índices Bioacústicos (audio WAV)</p>
                        <div class="index-bar-row">
                            <span class="index-bar-label" data-gauge-tip="Acoustic Complexity Index: variabilidad espectral de la grabación. Valores altos indican gran actividad biótica.">ACI</span>
                            <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.aci_avg??0)/2000*100,100)}%;background:linear-gradient(90deg,#60a5fa,#818cf8);"></div></div>
                            <span class="index-bar-val">${(r.aci_avg??0).toFixed(1)}</span>
                        </div>
                        <div class="index-bar-row">
                            <span class="index-bar-label" data-gauge-tip="Acoustic Diversity Index: diversidad de bandas de frecuencia ocupadas. Mayor ADI → mayor biodiversidad.">ADI</span>
                            <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.adi_avg??0)/3*100,100)}%;background:linear-gradient(90deg,#34d399,#059669);"></div></div>
                            <span class="index-bar-val">${(r.adi_avg??0).toFixed(3)}</span>
                        </div>
                        <div class="index-bar-row">
                            <span class="index-bar-label" data-gauge-tip="Acoustic Evenness Index: uniformidad del uso espectral. Valores bajos indican mayor riqueza sonora.">AEI</span>
                            <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.aei_avg??0)*100,100)}%;background:linear-gradient(90deg,#fbbf24,#f59e0b);"></div></div>
                            <span class="index-bar-val">${(r.aei_avg??0).toFixed(3)}</span>
                        </div>
                        <div class="index-bar-row">
                            <span class="index-bar-label" data-gauge-tip="Bioacoustic Index: energía acústica en la banda de biofonia (2–8 kHz). Indica intensidad de la actividad biológica.">BIO</span>
                            <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((r.bio_avg??0)/100*100,100)}%;background:linear-gradient(90deg,#f87171,#dc2626);"></div></div>
                            <span class="index-bar-val">${(r.bio_avg??0).toFixed(2)}</span>
                        </div>
                        <p class="text-muted mt-2 mb-0" style="font-size:0.68rem;">
                            <i class="bi bi-info-circle me-1"></i>Media de todos los archivos WAV disponibles.
                            Pasa el cursor sobre cada etiqueta para más info.
                        </p>
                    </div>
                </div>
            </div>

            <div class="col-lg-7">
                <div class="card border-0 bg-dark h-100">
                    <div class="card-body d-flex flex-column">
                        <p class="sci-section-title"><i class="bi bi-bar-chart-fill me-1"></i>Índices de Diversidad — Comparativa</p>
                        <div style="flex:1;min-height:0;">
                            <canvas id="scienceBarChart"></canvas>
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

        // ── Chart.js barras ───────────────────────────────────────────────
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
                            'rgba(96,165,250,0.75)','rgba(167,139,250,0.75)',
                            'rgba(52,211,153,0.75)','rgba(251,191,36,0.75)',
                            'rgba(232,121,249,0.75)'
                        ],
                        borderColor: ['#60a5fa','#a78bfa','#34d399','#fbbf24','#e879f9'],
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
                        y: { min:0, max:5, grid:{ color:'#ffffff0d' }, ticks:{ color:'#9ca3af', font:{ size:11 } } },
                        x: { grid:{ display:false }, ticks:{ color:'#e5e7eb', font:{ size:12 } } }
                    }
                }
            });
        }

        // ── Mapa Leaflet ──────────────────────────────────────────────────
        fetch("http://127.0.0.1:8000/analytics/map")
            .then(res => res.json())
            .then(mapData => {
                if (mapData.error) return;
                const map = L.map('biodiversityMap').setView([mapData.lat, mapData.lon], 13);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; OpenStreetMap'
                }).addTo(map);
                const marker = L.marker([mapData.lat, mapData.lon]).addTo(map);
                marker.bindPopup(`<b>${mapData.ciudad}</b><br>Biodiversidad H': <b>${mapData.shannon}</b>`).openPopup();
                const circleColor = mapData.shannon > 1.5 ? '#4ade80' : '#f87171';
                L.circle([mapData.lat, mapData.lon], {
                    color: circleColor, fillColor: circleColor,
                    fillOpacity: 0.15, radius: mapData.radio_km * 1000
                }).addTo(map);
            })
            .catch(() => {});

    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger mt-4">Error al cargar el análisis: ${e.message}</div>`;
    }
}

// ════════════════════════════════════════════════════════════════
// NODOS
// ════════════════════════════════════════════════════════════════

function renderNodesView(container) {
    let nodesHtml = '';
    MOCK_NODES.forEach(node => {
        const statusColor = node.status === 'online' ? 'success' : 'danger';
        const pulseClass  = node.status === 'online' ? 'animate-pulse' : '';
        nodesHtml += `<div class="col-md-4 mb-4"><div class="card bg-dark text-white border-0 shadow-sm node-card h-100"><div class="card-body"><div class="d-flex justify-content-between align-items-center mb-3"><h5 class="fw-bold m-0"><i class="bi bi-cpu text-info me-2"></i>${node.name}</h5><span class="badge bg-${statusColor} ${pulseClass}">${node.status.toUpperCase()}</span></div><p class="text-muted small mb-1"><i class="bi bi-geo-alt me-1"></i> ${node.location}</p><p class="text-muted small mb-1"><i class="bi bi-hdd-network me-1"></i> IP: ${node.ip}</p><p class="text-muted small mb-3"><i class="bi bi-record-circle me-1"></i> ID: <span class="font-monospace">${node.id}</span></p><button class="btn btn-outline-info btn-sm w-100" onclick="switchView('dashboard')"><i class="bi bi-activity me-1"></i> Ver Detecciones</button></div></div></div>`;
    });
    container.innerHTML = `
        <div class="row mb-4 animate-fade-in">
            <div class="col-12">
                <h3 class="fw-bold text-white"><i class="bi bi-router me-2 text-accent"></i>Red de Nodos (ARUs)</h3>
                <p class="text-muted">Estado en tiempo real de los dispositivos de monitorización de campo.</p>
            </div>
        </div>
        <div class="row animate-fade-in">${nodesHtml}</div>`;
}

// ════════════════════════════════════════════════════════════════
// ARRANQUE
// ════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('main-content');
    if (container) { container.className = "d-flex flex-column flex-grow-1 w-100"; container.innerHTML = getDashboardHTML(); }
    switchView('dashboard');
    setInterval(updateDashboard, 4000);
});