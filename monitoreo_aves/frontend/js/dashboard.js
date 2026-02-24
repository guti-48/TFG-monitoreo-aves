const API_URL = "http://127.0.0.1:8000/detections/";
const IMG_BASE_URL = "http://127.0.0.1:8000/spectrograms/";

// --- CONFIGURACIÓN DE IMÁGENES ---
const ASSETS_PATH = 'assets/'; 
const NOISE_MAP = {
    'Human vocal': 'human.png',
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
    
    const btnDash = document.getElementById('btn-dashboard');
    const btnNodes = document.getElementById('btn-nodes');
    const btnHist = document.getElementById('btn-history');
    const btnScience = document.getElementById('btn-science'); 

    if(btnDash) btnDash.className = 'list-group-item text-muted';
    if(btnNodes) btnNodes.className = 'list-group-item text-muted';
    if(btnHist) btnHist.className = 'list-group-item text-muted';
    if(btnScience) btnScience.className = 'list-group-item list-group-item-action bg-transparent text-white-50 border-0 py-3';

    const container = document.getElementById('main-content');
    // Aseguramos que el contenedor sea siempre elástico
    if(container) container.className = "d-flex flex-column flex-grow-1 w-100";

    if (viewName === 'dashboard' && btnDash) {
        btnDash.className = 'list-group-item active';
        container.innerHTML = getDashboardHTML();
        updateDashboard();
    }
    if (viewName === 'nodes' && btnNodes) btnNodes.className = 'list-group-item active';
    if (viewName === 'history' && btnHist) btnHist.className = 'list-group-item active';
    if (viewName === 'science' && btnScience) btnScience.className = 'list-group-item list-group-item-action bg-transparent text-white border-0 py-3 active-nav-item';
    
    if (viewName === 'nodes') renderNodesView(container);
    else if (viewName === 'history') renderHistoryView(container);
    else if (viewName === 'dashboard') updateDashboard();
    else if(viewName === 'science') renderScienceView(container);
}

// --- VISTA HISTÓRICO (TOTALMENTE ADAPTADA AL 100% DE LA PANTALLA) ---
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
            if(d.species.includes("Human") || d.species.includes("Motor") || d.species.includes("Noise")) icon = '<i class="bi bi-boombox text-warning"></i>';

            rowsHtml += `
            <tr>
                <td class="text-white-50 small">${d.id}</td>
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
                                <tr>
                                    <th class="py-3 ps-3">ID</th><th class="py-3">Fecha</th><th class="py-3">Especie</th>
                                    <th class="py-3">Nodo</th><th class="py-3">Confianza</th><th class="py-3 pe-3">Foto</th>
                                </tr>
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

// --- DASHBOARD TIEMPO REAL ---
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
            document.getElementById('noise-card').className = `card kpi-card border-start-${noiseColor}`;
            document.getElementById('noise-icon-box').className = `icon-box bg-${noiseColor}-subtle text-${noiseColor}`;
            document.getElementById('noise-icon').className = `bi ${noiseIcon} fs-3`;
        }

        const birdsOnly = sortedData.filter(d => 
            !d.species.toLowerCase().includes("noise") && !d.species.toLowerCase().includes("ruido") && !d.species.toLowerCase().includes("ambiente")
        );

        safeSetText('total-counter', birdsOnly.length); 

        if (birdsOnly.length > 0) {
            const latestBird = birdsOnly[0]; 
            safeSetText('last-activity', new Date(latestBird.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
            
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
    <h4 class="mb-4 fw-bold" id="dashboard-title">Monitorización Global</h4>
    <div class="row g-4 mb-4">
        <div class="col-md-3"><div class="card kpi-card border-start-success"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Detecciones Totales</p><h3 class="fw-bold mb-0" id="total-counter">0</h3></div><div class="icon-box bg-success-subtle text-success"><i class="bi bi-soundwave fs-3"></i></div></div></div></div>
        <div class="col-md-3"><div class="card kpi-card border-start-earth"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Especie Dominante</p><h4 class="fw-bold mb-0 fs-5 text-truncate" id="top-species">-</h4></div><div class="icon-box bg-earth-subtle text-earth"><i class="bi bi-trophy-fill fs-3"></i></div></div></div></div>
        <div class="col-md-3"><div class="card kpi-card border-start-info"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Última Actividad</p><h4 class="fw-bold mb-0 fs-5" id="last-activity">--:--</h4></div><div class="icon-box bg-info-subtle text-info"><i class="bi bi-clock-history fs-3"></i></div></div></div></div>
        <div class="col-md-3"><div class="card kpi-card border-start-secondary" id="noise-card"><div class="card-body d-flex align-items-center justify-content-between"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Nivel de Ruido</p><h4 class="fw-bold mb-0 fs-5" id="noise-metric">Calculando...</h4></div><div class="icon-box bg-secondary-subtle" id="noise-icon-box"><i class="bi bi-boombox fs-3" id="noise-icon"></i></div></div></div></div>
    </div>
    <div class="row g-4 mb-5">
        <div class="col-lg-7"><div class="card shadow-sm border-0 bg-dark overflow-hidden" style="min-height: 420px;"><div class="card-body p-0 d-flex flex-column h-100" id="live-feed-container"><div class="d-flex align-items-center justify-content-center flex-grow-1 text-muted"><p>Esperando datos...</p></div></div></div></div>
        <div class="col-lg-5"><div class="card h-100 shadow-sm border-0"><div class="card-header bg-transparent border-0 py-3"><h5 class="fw-bold m-0">Distribución de Especies</h5></div><div class="card-body"><canvas id="speciesChart" style="max-height: 300px;"></canvas></div></div></div>
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
        const res = await fetch(wikiUrl);
        const data = await res.json();
        const pages = data.query.pages;
        const pageId = Object.keys(pages)[0];
        if (pageId !== "-1" && pages[pageId].thumbnail) return pages[pageId].thumbnail.source;
    } catch (e) { console.error("Error Wiki", e); }
    return PLACEHOLDER_IMG;
}

// --- FOTO Y BARRA DE PROGRESO ARREGLADA ---
async function renderLiveFeedSplit(d) {
    const container = document.getElementById('live-feed-container');
    if (!container) return;
    const species = cleanName(d.species);
    const percent = (d.confidence * 100).toFixed(0);
    const spectrogramUrl = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
    const timeStr = new Date(d.timestamp).toLocaleTimeString();
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
                    <div class="progress w-100" style="height: 12px; background-color: rgba(255,255,255,0.2);">
                        <div class="progress-bar bg-success progress-bar-striped progress-bar-animated" role="progressbar" style="width: ${percent}%;"></div>
                    </div>
                </div>
                
                <div class="spectrogram-container mt-auto d-flex flex-column">
                    <img src="${spectrogramUrl}" class="spectrogram-img" onerror="this.style.opacity='0.3';">
                    <div class="bg-dark text-muted small px-3 py-2 d-flex justify-content-between align-items-center border-top border-secondary mt-auto">
                        <span><i class="bi bi-soundwave me-2"></i>Espectrograma</span>
                        <span class="font-monospace text-white-50 text-truncate" style="max-width: 50%;" title="${d.filename}">${d.filename}</span>
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

// --- VISTA ANÁLISIS ECO (TOTALMENTE ADAPTADA AL 100% DE LA PANTALLA) ---
async function renderScienceView(container) {
    container.innerHTML = `<div class="d-flex justify-content-center align-items-center py-5"><div class="spinner-grow text-info" role="status"></div><span class="ms-3 text-white">Procesando datos del nodo...</span></div>`;

    try {
        const response = await fetch("http://127.0.0.1:8000/analytics/biodiversity");
        const report = await response.json();

        if (!report || report.length === 0) {
            container.innerHTML = `<div class="alert alert-warning text-center">Esperando detecciones reales del nodo...</div>`;
            return;
        }

        const r = report[0]; 
        let colorCalidad = r.calidad === 'Excelente' ? 'success' : (r.calidad === 'Moderado' ? 'warning' : 'danger');

        container.innerHTML = `
            <div class="row mb-4 animate-fade-in text-center">
                <div class="col-12">
                    <h3 class="fw-bold text-white"><i class="bi bi-cpu me-2 text-info"></i>Análisis Científico del Nodo</h3>
                </div>
            </div>
            <div class="row justify-content-center animate-fade-in mb-4">
                <div class="col-lg-8">
                    <div class="card shadow-sm border-0 bg-dark text-white">
                        <div class="card-header border-0 py-3 d-flex justify-content-between align-items-center">
                            <h5 class="mb-0 fw-bold"><i class="bi bi-geo-alt-fill me-2 text-info"></i>${r.zona}</h5><span class="badge bg-${colorCalidad}">${r.calidad}</span>
                        </div>
                        <div class="card-body">
                            <div class="row text-center g-3">
                                <div class="col-4"><h6 class="text-muted small text-uppercase">Riqueza (S)</h6><h3 class="fw-bold">${r.riqueza}</h3></div>
                                <div class="col-4"><h6 class="text-muted small text-uppercase">Abundancia</h6><h3 class="fw-bold">${r.abundancia}</h3></div>
                                <div class="col-4"><h6 class="text-muted small text-uppercase">Shannon (H')</h6><h3 class="fw-bold text-${colorCalidad}">${r.shannon}</h3></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="row animate-fade-in mb-4">
                <div class="col-lg-6 mb-3">
                    <div class="card border-0 shadow-sm bg-dark text-white h-100">
                        <div class="card-header border-0 py-3"><h6 class="fw-bold m-0">Huella Acústica (WAV)</h6></div>
                        <div class="card-body"><canvas id="radarChart" style="max-height: 250px;"></canvas></div>
                    </div>
                </div>
                <div class="col-lg-6 mb-3">
                    <div class="card border-0 shadow-sm bg-dark text-white h-100">
                        <div class="card-header border-0 py-3"><h6 class="fw-bold m-0">Equilibrio del Ecosistema (BBDD)</h6></div>
                        <div class="card-body"><canvas id="scienceChart" style="max-height: 250px;"></canvas></div>
                    </div>
                </div>
            </div>
            
            <div class="row animate-fade-in flex-grow-1" style="min-height: 400px;">
                <div class="col-12 d-flex flex-column">
                    <div class="card border-0 shadow-sm bg-dark text-white flex-grow-1 d-flex flex-column">
                        <div class="card-header border-0 py-3"><h5 class="fw-bold m-0"><i class="bi bi-map-fill me-2 text-info"></i>Cobertura Geoespacial</h5></div>
                        <div class="card-body p-0 flex-grow-1 position-relative">
                            <div id="biodiversityMap" style="position: absolute; top:0; bottom:0; left:0; right:0; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px; z-index: 1;"></div>
                        </div>
                    </div>
                </div>
            </div>`;

        new Chart(document.getElementById('radarChart').getContext('2d'), { type: 'radar', data: { labels: ['ACI', 'ADI', 'AEI', 'BIO', 'NDSI'], datasets: [{ label: 'Perfil Acústico', data: [r.aci_avg/100, r.adi_avg, r.aei_avg, r.bio_avg/10, r.ndsi_avg+1], backgroundColor: 'rgba(54, 162, 235, 0.2)', borderColor: 'rgba(54, 162, 235, 1)', pointBackgroundColor: 'rgba(54, 162, 235, 1)' }] }, options: { responsive: true, maintainAspectRatio: false, scales: { r: { ticks: { display: false }, grid: { color: '#ffffff20' }, pointLabels: { color: '#aaa' } } }, plugins: { legend: { display: false } } } });
        new Chart(document.getElementById('scienceChart').getContext('2d'), { type: 'bar', data: { labels: ['Shannon (Diversidad)', 'Pielou (Equilibrio)', 'Simpson (Dominancia)'], datasets: [{ label: "Índices", data: [r.shannon, r.pielou, r.simpson], backgroundColor: ['#4bc0c0', '#9966ff', '#ff9f40'] }] }, options: { responsive: true, maintainAspectRatio: false, scales: { y: { grid: { color: '#ffffff10' }, ticks: { color: '#aaa' } }, x: { grid: { display: false }, ticks: { color: '#fff' } } }, plugins: { legend: { display: false } } } });

        fetch("http://127.0.0.1:8000/analytics/map").then(res => res.json()).then(mapData => {
            if(mapData.error) return;
            const map = L.map('biodiversityMap').setView([mapData.lat, mapData.lon], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap' }).addTo(map);
            const marker = L.marker([mapData.lat, mapData.lon]).addTo(map);
            marker.bindPopup(`<b>Nodo: ${mapData.ciudad}</b><br>Biodiversidad (H'): ${mapData.shannon}`).openPopup();
            const circleColor = mapData.shannon > 1.5 ? '#28a745' : '#dc3545';
            L.circle([mapData.lat, mapData.lon], { color: circleColor, fillColor: circleColor, fillOpacity: 0.2, radius: mapData.radio_km * 1000 }).addTo(map);
        });
    } catch (e) { container.innerHTML = `<div class="alert alert-danger">Error: ${e.message}</div>`; }
}

function renderNodesView(container) {
    let nodesHtml = '';
    MOCK_NODES.forEach(node => {
        const statusColor = node.status === 'online' ? 'success' : 'danger';
        const pulseClass = node.status === 'online' ? 'animate-pulse' : '';
        nodesHtml += `<div class="col-md-4 mb-4"><div class="card bg-dark text-white border-0 shadow-sm node-card h-100"><div class="card-body"><div class="d-flex justify-content-between align-items-center mb-3"><h5 class="fw-bold m-0"><i class="bi bi-cpu text-info me-2"></i>${node.name}</h5><span class="badge bg-${statusColor} ${pulseClass}">${node.status.toUpperCase()}</span></div><p class="text-muted small mb-1"><i class="bi bi-geo-alt me-1"></i> ${node.location}</p><p class="text-muted small mb-1"><i class="bi bi-hdd-network me-1"></i> IP: ${node.ip}</p><p class="text-muted small mb-3"><i class="bi bi-record-circle me-1"></i> ID: <span class="font-monospace">${node.id}</span></p><button class="btn btn-outline-info btn-sm w-100" onclick="switchView('dashboard')"><i class="bi bi-activity me-1"></i> Ver Detecciones</button></div></div></div>`;
    });
    container.innerHTML = `<div class="row mb-4 animate-fade-in"><div class="col-12"><h3 class="fw-bold text-white"><i class="bi bi-router me-2 text-accent"></i>Red de Nodos (ARUs)</h3><p class="text-muted">Estado en tiempo real de los dispositivos de monitorización de campo.</p></div></div><div class="row animate-fade-in">${nodesHtml}</div>`;
}

// --- ARRANQUE ---
document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('main-content');
    if (container) { container.className = "d-flex flex-column flex-grow-1 w-100"; container.innerHTML = getDashboardHTML(); }
    switchView('dashboard');
    setInterval(updateDashboard, 4000);
});