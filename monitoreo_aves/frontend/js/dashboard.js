const API_URL = "http://127.0.0.1:8000/detections/";
const IMG_BASE_URL = "http://127.0.0.1:8000/spectrograms/";

// --- CONFIGURACIÓN DE IMÁGENES ---
const ASSETS_PATH = 'images/'; 
const NOISE_MAP = {
    'Human vocal': 'human.jpg',
    'Motor': 'ruido_amb.png', 
};
const PLACEHOLDER_IMG = ASSETS_PATH + 'placeholder.jpg';

// --- ESTADO DE LA APP ---
let currentView = 'dashboard'; 
let activeNodeFilter = null;
let myChart = null;
let intervalId = null;

// --- DATOS SIMULADOS DE NODOS ---
const MOCK_NODES = [
    { id: 'RaspberryPi_01', name: 'Nodo Algeciras', location: 'Cádiz, ES', status: 'online', lat: 37.38, lon: -5.97, ip: '192.168.1.35' },
    { id: 'RaspberryPi_Sanguesa', name: 'Nodo Sangüesa', location: 'Navarra, ES', status: 'offline', lat: 42.57, lon: -1.28, ip: '10.0.0.5' },
    { id: 'RaspberryPi_Madrid', name: 'Nodo Bilbao', location: 'Bilbao, EH', status: 'offline', lat: 40.41, lon: -3.70, ip: '192.168.0.10' }
];

//FUNCIÓN PRINCIPAL DE CAMBIO DE VISTA
function switchView(viewName, nodeFilter = null) {
    currentView = viewName;
    activeNodeFilter = nodeFilter;
    
    // Gestión visual de botones
    const btnDash = document.getElementById('btn-dashboard');
    const btnNodes = document.getElementById('btn-nodes');
    const btnHist = document.getElementById('btn-history'); 

    // Resetear clases
    if(btnDash) btnDash.className = 'list-group-item text-muted';
    if(btnNodes) btnNodes.className = 'list-group-item text-muted';
    if(btnHist) btnHist.className = 'list-group-item text-muted';

    // Activar el actual
    if (viewName === 'dashboard' && btnDash) {
        btnDash.className = 'list-group-item active';
        // Si venimos de otra vista, reconstruimos el dashboard
        const container = document.getElementById('main-content');
        container.innerHTML = getDashboardHTML();
        updateDashboard();
    }
    if (viewName === 'nodes' && btnNodes) btnNodes.className = 'list-group-item active';
    if (viewName === 'history' && btnHist) btnHist.className = 'list-group-item active';

    const container = document.getElementById('main-content');
    
    // Renderizado según la vista
    if (viewName === 'nodes') {
        renderNodesView(container);
    } else if (viewName === 'history') {
        renderHistoryView(container);
    } else if (viewName === 'dashboard') {
        // El dashboard ya se gestiona en updateDashboard, pero forzamos update si cambiamos filtro
        updateDashboard();
    }
}

// --- VISTA HISTÓRICO (TABLA GIGANTE) ---
async function renderHistoryView(container) {
    container.innerHTML = `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="spinner-border text-success" role="status"></div>
            <span class="ms-3 text-muted">Cargando base de datos completa...</span>
        </div>`;

    try {
        const response = await fetch(`${API_URL}?limit=500`);
        const data = await response.json();
        const sortedData = data.reverse(); 

        let rowsHtml = '';
        sortedData.forEach(d => {
            const timeDate = new Date(d.timestamp);
            const dateStr = timeDate.toLocaleDateString();
            const timeStr = timeDate.toLocaleTimeString();
            const imgUrl = `${IMG_BASE_URL}${d.filename.replace('.wav', '.png')}`;
            const clean = cleanName(d.species);

            let icon = '<i class="bi bi-music-note-beamed text-success"></i>';
            if(d.species.includes("Human") || d.species.includes("Motor")) icon = '<i class="bi bi-boombox text-warning"></i>';

            rowsHtml += `
            <tr>
                <td><span class="font-monospace text-muted small">${d.id}</span></td>
                <td>${dateStr} <small class="text-muted">${timeStr}</small></td>
                <td><div class="d-flex align-items-center"><div class="me-2">${icon}</div><span class="fw-bold text-white">${clean}</span></div></td>
                <td>${d.device_name || 'RaspberryPi'}</td>
                <td>
                    <div class="progress" style="height: 6px; width: 100px;">
                        <div class="progress-bar bg-${d.confidence > 0.8 ? 'success' : 'warning'}" role="progressbar" style="width: ${d.confidence * 100}%"></div>
                    </div>
                </td>
                <td><a href="${imgUrl}" target="_blank" class="btn btn-sm btn-outline-secondary"><i class="bi bi-image"></i> Ver</a></td>
            </tr>`;
        });

        container.innerHTML = `
            <div class="row mb-4 animate-fade-in">
                <div class="col-12 d-flex justify-content-between align-items-center">
                    <div>
                        <h3 class="fw-bold text-white"><i class="bi bi-database-fill me-2 text-accent"></i>Histórico</h3>
                        <p class="text-muted">Total registros: ${sortedData.length}</p>
                    </div>
                    <button class="btn btn-success" onclick="downloadCSV()"><i class="bi bi-file-earmark-spreadsheet me-2"></i>Exportar Excel</button>
                </div>
            </div>
            <div class="card shadow-sm border-0 animate-fade-in">
                <div class="card-body p-0">
                    <div class="table-responsive">
                        <table class="table table-hover table-striped align-middle mb-0">
                            <thead class="bg-dark text-white text-uppercase small"><tr><th>ID</th><th>Fecha</th><th>Especie</th><th>Nodo</th><th>Confianza</th><th>Foto</th></tr></thead>
                            <tbody>${rowsHtml}</tbody>
                        </table>
                    </div>
                </div>
            </div>`;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`;
    }
}

// --- VISTA NODOS ---
function renderNodesView(container) {
    let cardsHtml = '';
    MOCK_NODES.forEach(node => {
        let statusColor = node.status === 'online' ? 'success' : 'secondary';
        cardsHtml += `
        <div class="col-md-4">
            <div class="card h-100 border-0 shadow-sm node-card" onclick="switchView('dashboard', '${node.id}')" style="cursor: pointer;">
                <div class="card-body">
                    <div class="d-flex justify-content-between mb-3"><div class="icon-box bg-dark text-${statusColor} border border-${statusColor} rounded-circle"><i class="bi bi-hdd-network fs-4"></i></div><span class="badge bg-${statusColor}-subtle text-${statusColor} border border-${statusColor} px-3 rounded-pill">${node.status}</span></div>
                    <h5 class="fw-bold text-white mb-1">${node.name}</h5>
                    <p class="text-muted small mb-3">${node.location}</p>
                    <button class="btn btn-outline-${statusColor} w-100 btn-sm">Ver Telemetría</button>
                </div>
            </div>
        </div>`;
    });
    container.innerHTML = `<div class="row mb-4"><div class="col-12"><h3 class="fw-bold text-white">Mis Nodos</h3></div></div><div class="row g-4 animate-fade-in">${cardsHtml}</div>`;
}

//VISTA DASHBOARD (TIEMPO REAL)
async function updateDashboard() {
    if (currentView !== 'dashboard') return; 

    try {
        const response = await fetch(API_URL);
        let data = await response.json();
        
        // Filtro por nodo (si está activo)
        if (activeNodeFilter) {
            data = data.filter(d => d.device_name === activeNodeFilter);
            const nodeName = MOCK_NODES.find(n => n.id === activeNodeFilter)?.name || activeNodeFilter;
            const titleEl = document.getElementById('dashboard-title');
            if(titleEl) titleEl.innerHTML = `<i class="bi bi-funnel-fill me-2 text-warning"></i>${nodeName}`;
        } else {
             const titleEl = document.getElementById('dashboard-title');
             if(titleEl) titleEl.innerHTML = `<i class="bi bi-broadcast text-success me-2 animate-pulse"></i>Monitorización Global`;
        }

        if (!data || data.length === 0) {
            safeSetText('total-counter', '0');
            return;
        }

        const sortedData = data.reverse(); // Aquí están TODOS (Pájaros + Ruido)

        // Calculamos volumen promedio basado en la nueva columna 'amplitude'
        let totalAmp = 0;
        sortedData.forEach(d => { totalAmp += (d.amplitude || 0); });
        
        // Ajusta el factor 500 según tu micro
        let avgAmp = (sortedData.length > 0) ? (totalAmp / sortedData.length) * 500 : 0;
        if (avgAmp > 100) avgAmp = 100;

        let noiseLabel = "Silencioso";
        let noiseColor = "success"; 
        let noiseIcon = "bi-tree-fill";

        if (avgAmp > 10) { noiseLabel = "Moderado"; noiseColor = "warning"; noiseIcon = "bi-people-fill"; }
        if (avgAmp > 30) { noiseLabel = "Ruidoso"; noiseColor = "danger"; noiseIcon = "bi-speaker-fill"; }

        const noiseEl = document.getElementById('noise-metric');
        if (noiseEl) {
            noiseEl.innerText = `${noiseLabel} (Vol: ${avgAmp.toFixed(0)})`;
            noiseEl.className = `fw-bold mb-0 fs-5 text-${noiseColor}`;
            document.getElementById('noise-card').className = `card kpi-card border-start-${noiseColor}`;
            document.getElementById('noise-icon-box').className = `icon-box bg-${noiseColor}-subtle text-${noiseColor}`;
            document.getElementById('noise-icon').className = `bi ${noiseIcon} fs-3`;
        }

        const birdsOnly = sortedData.filter(d => 
            !d.species.includes("Noise") && 
            !d.species.includes("Ruido") &&
            !d.species.includes("Ambiente")
        );

        // Actualizamos los contadores
        safeSetText('total-counter', birdsOnly.length); // Muestra total de AVES, no de registros totales

        if (birdsOnly.length > 0) {
            const latestBird = birdsOnly[0];
            
            // Última actividad, de pajaros no de ruido
            safeSetText('last-activity', new Date(latestBird.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
            
            // Especie dominante, de pajaros
            const counts = {};
            birdsOnly.forEach(d => { counts[d.species] = (counts[d.species] || 0) + 1; });
            const topSpecies = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
            safeSetText('top-species', cleanName(topSpecies));

            // tarjeta que nos interesa mostrar el pajato solo
            await renderLiveFeedSplit(latestBird);

            renderTable(birdsOnly.slice(0, 10));

            // grafica con los pajaros
            updateChart(counts);
        } else {
            // Si solo hay ruido y ningún pájaro todavía...
            console.log("Solo hay ruido ambiente, esperando aves...");
        }

    } catch (error) { console.error("Error Dashboard:", error); }
}

function getDashboardHTML() {
    return `
    <h4 class="mb-4 fw-bold" id="dashboard-title">Monitorización Global</h4>
    <div class="row g-4 mb-4">
        <div class="col-md-3">
            <div class="card kpi-card border-start-success">
                <div class="card-body d-flex align-items-center justify-content-between">
                    <div><p class="text-muted small text-uppercase mb-1 fw-bold">Detecciones Totales</p><h3 class="fw-bold mb-0" id="total-counter">0</h3></div>
                    <div class="icon-box bg-success-subtle text-success"><i class="bi bi-soundwave fs-3"></i></div>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card kpi-card border-start-earth">
                <div class="card-body d-flex align-items-center justify-content-between">
                    <div><p class="text-muted small text-uppercase mb-1 fw-bold">Especie Dominante</p><h4 class="fw-bold mb-0 fs-5 text-truncate" id="top-species">-</h4></div>
                    <div class="icon-box bg-earth-subtle text-earth"><i class="bi bi-trophy-fill fs-3"></i></div>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card kpi-card border-start-info">
                <div class="card-body d-flex align-items-center justify-content-between">
                    <div><p class="text-muted small text-uppercase mb-1 fw-bold">Última Actividad</p><h4 class="fw-bold mb-0 fs-5" id="last-activity">--:--</h4></div>
                    <div class="icon-box bg-info-subtle text-info"><i class="bi bi-clock-history fs-3"></i></div>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card kpi-card border-start-secondary" id="noise-card">
                <div class="card-body d-flex align-items-center justify-content-between">
                    <div>
                        <p class="text-muted small text-uppercase mb-1 fw-bold">Nivel de Ruido</p>
                        <h4 class="fw-bold mb-0 fs-5" id="noise-metric">Calculando...</h4>
                    </div>
                    <div class="icon-box bg-secondary-subtle" id="noise-icon-box">
                        <i class="bi bi-boombox fs-3" id="noise-icon"></i>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <div class="row g-4 mb-5">
        <div class="col-lg-7"><div class="card h-100 shadow-sm main-detection-split border-0 overflow-hidden"><div class="card-body p-0" id="live-feed-container"><div class="d-flex align-items-center justify-content-center h-100 text-muted"><p>Esperando datos...</p></div></div></div></div>
        <div class="col-lg-5"><div class="card h-100 shadow-sm border-0"><div class="card-header bg-transparent border-0 py-3"><h5 class="fw-bold m-0">Distribución de Especies</h5></div><div class="card-body"><canvas id="speciesChart" style="max-height: 300px;"></canvas></div></div></div>
    </div>
    <div class="row"><div class="col-12"><div class="card shadow-sm border-0"><div class="card-header bg-transparent border-0 py-3"><h5 class="fw-bold m-0">Registro Reciente</h5></div><div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead class="bg-dark-subtle text-uppercase small"><tr><th class="ps-4">Hora</th><th>Especie</th><th>Confianza</th><th>Espectrograma</th><th class="text-end pe-4">ID</th></tr></thead><tbody id="history-table-body"></tbody></table></div></div></div></div>`;
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

    if (NOISE_MAP[clean] || clean.includes("Human") || clean.includes("Motor")) {
        if (clean.includes("Human")) return ASSETS_PATH + 'human.jpg';
        if (clean.includes("Motor") || clean.includes("Ruido")) return ASSETS_PATH + 'ruido_amb.png'; 
        return PLACEHOLDER_IMG;
    }
    try {
        const wikiUrl = `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(clean)}&prop=pageimages&format=json&pithumbsize=600&redirects=1&origin=*`;
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
    const spectrogramUrl = `${IMG_BASE_URL}${d.filename.replace('.wav', '.png')}`;
    const timeStr = new Date(d.timestamp).toLocaleTimeString();
    
    // Solo si cambia la especie, buscamos foto nueva (optimización simple)
    // Para simplificar, la pedimos siempre aquí:
    const speciesPhotoUrl = await getSpeciesImageUrl(d.species);

    container.innerHTML = `
        <div class="main-detection-split">
            <div class="split-photo" style="background-image: url('${speciesPhotoUrl}');">
                <div class="photo-overlay-label"><i class="bi bi-camera-fill me-2"></i>Imagen de Referencia</div>
            </div>
            <div class="split-info">
                <h6 class="text-muted text-uppercase fw-bold mb-1">Detección en vivo - ${timeStr}</h6>
                <h2 class="display-6 fw-bold text-white mb-3">${species}</h2>
                <div class="d-flex align-items-center mb-2"><span class="badge bg-success me-2 fs-6">${percent}% Confianza</span><div class="progress flex-grow-1" style="height: 8px; background-color: #333;"><div class="progress-bar bg-success" role="progressbar" style="width: ${percent}%"></div></div></div>
                <div class="spectrogram-container"><img src="${spectrogramUrl}" class="img-fluid w-100" style="height: 200px; object-fit: fill; filter: contrast(1.1) brightness(1.1);" onerror="this.style.opacity='0.3';"><div class="bg-dark text-muted small px-2 py-1 d-flex justify-content-between"><span><i class="bi bi-soundwave me-2"></i>Espectrograma</span><span class="font-monospace text-white-50">${d.filename}</span></div></div>
            </div>
        </div>`;
}

function renderTable(data) {
    const tbody = document.getElementById('history-table-body');
    if (!tbody) return;
    tbody.innerHTML = "";
    data.forEach(d => {
        const imgUrl = `${IMG_BASE_URL}${d.filename.replace('.wav', '.png')}`;
        const clean = cleanName(d.species);
        let icon = '<i class="bi bi-feather text-success me-2"></i>';
        if(NOISE_MAP[clean] || d.species.includes("Human") || d.species.includes("Motor")) icon = '<i class="bi bi-boombox text-muted me-2"></i>';
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
    const natureColors = ['#2E7D32', '#C49A6C', '#0288D1', '#689F38', '#8D6E63'];
    myChart = new Chart(ctx, { type: 'doughnut', data: { labels, datasets: [{ data: values, backgroundColor: natureColors, borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#e0e0e0' } } } } });
}

function safeSetText(id, text) { const el = document.getElementById(id); if (el) el.innerText = text; }
function cleanName(name) { if (!name) return "Desconocido"; let cleaned = name.split('_')[1] || name; return cleaned.charAt(0).toUpperCase() + cleaned.slice(1); }

// --- ARRANQUE ---
document.addEventListener('DOMContentLoaded', () => {
    // IMPORTANTE: Primero inyectamos el HTML del dashboard
    const container = document.getElementById('main-content');
    if (container) container.innerHTML = getDashboardHTML();
    // Luego activamos la vista por defecto
    switchView('dashboard');
    // Y el bucle
    setInterval(updateDashboard, 4000);
});