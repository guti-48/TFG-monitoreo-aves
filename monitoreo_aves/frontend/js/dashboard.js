const API_URL = "http://127.0.0.1:8000/detections/";
const IMG_BASE_URL = "http://127.0.0.1:8000/spectrograms/";

//CONFIGURACIÓN DE IMÁGENES
const ASSETS_PATH = 'images/'; 
const NOISE_MAP = {
    'Human vocal': 'human.jpg',
    'Motor': 'ruido_amb.png', 
};
const PLACEHOLDER_IMG = ASSETS_PATH + 'placeholder.jpg';

//ESTADO DE LA APP
let currentView = 'dashboard'; 
let activeNodeFilter = null;   
let myChart = null;
let intervalId = null;

//DATOS SIMULADOS DE NODOS
const MOCK_NODES = [
    { id: 'RaspberryPi_01', name: 'Nodo Sevilla', location: 'Sevilla, ES', status: 'online', lat: 37.38, lon: -5.97, ip: '192.168.1.35' },
    { id: 'RaspberryPi_Sanguesa', name: 'Nodo Sangüesa', location: 'Navarra, ES', status: 'offline', lat: 42.57, lon: -1.28, ip: '10.0.0.5' },
    { id: 'RaspberryPi_Bilbo', name: 'Nodo Bilbo', location: 'Bilbo, EH', status: 'offline', lat: 43.41, lon: -3.70, ip: '192.168.0.10' }
];

//FUNCIÓN PRINCIPAL DE CAMBIO DE VISTA 
function switchView(viewName, nodeFilter = null) {
    currentView = viewName;
    activeNodeFilter = nodeFilter;
    
    // Actualizar botones del menú
    document.getElementById('btn-dashboard').className = `list-group-item ${viewName === 'dashboard' ? 'active' : 'text-muted'}`;
    document.getElementById('btn-nodes').className = `list-group-item ${viewName === 'nodes' ? 'active' : 'text-muted'}`;

    const container = document.getElementById('main-content');
    
    if (viewName === 'nodes') {
        renderNodesView(container);
    } else {
        // Si vamos al dashboard, reconstruimos la estructura original
        container.innerHTML = getDashboardHTML();
        // Forzamos actualización inmediata
        updateDashboard(); 
    }
}

// --- RENDERIZADO DE LA LISTA DE NODOS ---
function renderNodesView(container) {
    let cardsHtml = '';
    
    MOCK_NODES.forEach(node => {
        // Colores según estado
        let statusColor = 'secondary';
        let statusIcon = 'dash-circle';
        if (node.status === 'online') { statusColor = 'success'; statusIcon = 'wifi'; }
        if (node.status === 'offline') { statusColor = 'danger'; statusIcon = 'x-circle'; }
        if (node.status === 'maintenance') { statusColor = 'warning'; statusIcon = 'tools'; }

        cardsHtml += `
        <div class="col-md-4">
            <div class="card h-100 border-0 shadow-sm node-card" onclick="switchView('dashboard', '${node.id}')" style="cursor: pointer; transition: transform 0.2s;">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start mb-3">
                        <div class="icon-box bg-dark text-${statusColor} border border-${statusColor} rounded-circle">
                            <i class="bi bi-${statusIcon} fs-4"></i>
                        </div>
                        <span class="badge bg-${statusColor}-subtle text-${statusColor} border border-${statusColor} px-3 rounded-pill text-uppercase small">
                            ${node.status}
                        </span>
                    </div>
                    <h5 class="fw-bold text-white mb-1">${node.name}</h5>
                    <p class="text-muted small mb-3"><i class="bi bi-geo-alt me-1"></i>${node.location}</p>
                    
                    <div class="bg-dark rounded p-2 mb-3">
                        <div class="d-flex justify-content-between small text-muted">
                            <span>IP:</span> <span class="font-monospace text-white">${node.ip}</span>
                        </div>
                        <div class="d-flex justify-content-between small text-muted">
                            <span>ID:</span> <span class="font-monospace text-white">${node.id}</span>
                        </div>
                    </div>
                    <button class="btn btn-outline-${statusColor} w-100 btn-sm">
                        <i class="bi bi-eye me-2"></i>Ver Datos
                    </button>
                </div>
            </div>
        </div>`;
    });

    container.innerHTML = `
        <div class="row mb-4 animate-fade-in">
            <div class="col-12">
                <h3 class="fw-bold text-white"><i class="bi bi-hdd-network me-2 text-accent"></i>Gestión de Nodos</h3>
                <p class="text-muted">Selecciona un dispositivo para ver su telemetría en tiempo real.</p>
            </div>
        </div>
        <div class="row g-4 animate-fade-in">${cardsHtml}</div>
    `;
}

//LÓGICA DEL DASHBOARD
async function updateDashboard() {
    if (currentView !== 'dashboard') return; // No actualizar si estamos viendo nodos

    try {
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error("API Backend desconectada");
        
        let data = await response.json();
        
        // --- FILTRADO POR NODO ---
        // Si hemos entrado en un nodo específico, filtramos los datos
        let filterTitle = "Monitorización Global";
        if (activeNodeFilter) {
            // Buscamos el nombre bonito del nodo
            const nodeObj = MOCK_NODES.find(n => n.id === activeNodeFilter);
            const nodeName = nodeObj ? nodeObj.name : activeNodeFilter;
            
            filterTitle = `<i class="bi bi-funnel-fill me-2 text-warning"></i>${nodeName}`;
            
            // FILTRAMOS LOS DATOS: Solo mostramos lo que venga de este device_name
            data = data.filter(d => d.device_name === activeNodeFilter);
        }

        // Actualizar título del dashboard
        const titleEl = document.getElementById('dashboard-title');
        if(titleEl) titleEl.innerHTML = filterTitle;

        if (!data || data.length === 0) {
            console.log("No hay datos para mostrar (o filtro vacío)."); 
            // Limpiar interfaz si no hay datos
            safeSetText('total-counter', '0');
            return;
        }

        const sortedData = data.reverse(); // Más recientes primero
        const latest = sortedData[0];

        // 1. KPIs
        safeSetText('total-counter', sortedData.length);
        safeSetText('last-activity', new Date(latest.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
        
        const counts = {};
        sortedData.forEach(d => { counts[d.species] = (counts[d.species] || 0) + 1; });
        const topSpecies = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
        safeSetText('top-species', cleanName(topSpecies));

        // 2. Tarjeta Principal
        await renderLiveFeedSplit(latest);

        // 3. Tabla y Gráfica
        renderTable(sortedData.slice(0, 10));
        updateChart(counts);

    } catch (error) {
        console.error("Error Dashboard:", error);
    }
}

// --- TEMPLATE HTML DEL DASHBOARD (Para restaurarlo al volver de Nodos) ---
function getDashboardHTML() {
    return `
    <h4 class="mb-4 fw-bold" id="dashboard-title">Monitorización Activa</h4>
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
                    <div><p class="text-muted small text-uppercase mb-1 fw-bold">Especie Dominante</p><h4 class="fw-bold mb-0 fs-5 text-truncate" id="top-species" style="max-width: 150px;">-</h4></div>
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
            <div class="card kpi-card border-start-earth"><div class="card-body d-flex align-items-center justify-content-between opacity-50"><div><p class="text-muted small text-uppercase mb-1 fw-bold">Nivel de Ruido</p><h4 class="fw-bold mb-0 fs-5">Próximamente</h4></div><div class="icon-box bg-secondary-subtle"><i class="bi bi-boombox fs-3"></i></div></div></div>
        </div>
    </div>

    <div class="row g-4 mb-5">
        <div class="col-lg-7">
            <div class="card h-100 shadow-sm main-detection-card border-0 overflow-hidden">
                <div class="card-header bg-transparent border-0 d-flex justify-content-between align-items-center py-3">
                    <h5 class="fw-bold m-0"><i class="bi bi-binoculars-fill me-2 text-success"></i>Último Avistamiento</h5>
                    <span class="badge bg-danger animate-pulse px-3"><i class="bi bi-circle-fill small me-2"></i>LIVE FEED</span>
                </div>
                <div class="card-body p-0" id="live-feed-container">
                    <div class="d-flex align-items-center justify-content-center h-100 text-muted py-5"><div class="text-center"><i class="bi bi-ear-fill fs-1 mb-3 d-block opacity-50"></i><p>Esperando datos...</p></div></div>
                </div>
            </div>
        </div>
        <div class="col-lg-5">
            <div class="card h-100 shadow-sm border-0">
                <div class="card-header bg-transparent border-0 py-3"><h5 class="fw-bold m-0"><i class="bi bi-pie-chart-fill me-2 text-earth"></i>Distribución de Especies</h5></div>
                <div class="card-body"><canvas id="speciesChart" style="max-height: 300px;"></canvas></div>
            </div>
        </div>
    </div>

    <div class="row">
        <div class="col-12">
            <div class="card shadow-sm border-0">
                <div class="card-header bg-transparent border-0 py-3 d-flex justify-content-between align-items-center"><h5 class="fw-bold m-0">Registro Reciente</h5><button class="btn btn-sm btn-outline-secondary"><i class="bi bi-download me-2"></i>Exportar CSV</button></div>
                <div class="table-responsive"><table class="table table-hover align-middle mb-0" style="border-color: #333;"><thead class="bg-dark-subtle text-uppercase small text-muted fw-bold"><tr><th class="ps-4">Hora</th><th>Especie / Fuente</th><th>Confianza</th><th>Espectrograma</th><th class="text-end pe-4">ID</th></tr></thead><tbody id="history-table-body" class="border-top-0"></tbody></table></div>
            </div>
        </div>
    </div>`;
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
    
    // Solo actualizamos si no estamos ya cargando (opcional)
    const speciesPhotoUrl = await getSpeciesImageUrl(d.species);

    container.innerHTML = `
        <div class="main-detection-split">
            <div class="split-photo" style="background-image: url('${speciesPhotoUrl}');">
                <div class="photo-overlay-label"><i class="bi bi-camera-fill me-2"></i>Imagen de Referencia</div>
            </div>
            <div class="split-info">
                <h6 class="text-muted text-uppercase fw-bold mb-1">Detección en vivo - ${timeStr}</h6>
                <h2 class="display-6 fw-bold text-white mb-3">${species}</h2>
                <div class="d-flex align-items-center mb-2">
                    <span class="badge bg-success me-2 fs-6">${percent}% Confianza</span>
                    <div class="progress flex-grow-1" style="height: 8px; background-color: #333;"><div class="progress-bar bg-success" role="progressbar" style="width: ${percent}%"></div></div>
                </div>
                <div class="spectrogram-container">
                <img src="${spectrogramUrl}" 
                     class="img-fluid w-100" 
                     style="height: 200px; object-fit: fill; filter: contrast(1.1) brightness(1.1);" 
                     onerror="this.style.opacity='0.3';">
                     
                <div class="bg-dark text-muted small px-2 py-1 d-flex justify-content-between">
                    <span><i class="bi bi-soundwave me-2"></i>Análisis Espectral</span>
                    <span class="font-monospace text-white-50">${d.filename}</span>
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
        const imgUrl = `${IMG_BASE_URL}${d.filename.replace('.wav', '.png')}`;
        const speciesClean = cleanName(d.species);
        let iconHtml = '<i class="bi bi-feather text-success me-2"></i>';
        if (NOISE_MAP[speciesClean] || d.species.includes("Human") || d.species.includes("Motor")) iconHtml = '<i class="bi bi-boombox text-muted me-2"></i>';
        
        tbody.innerHTML += `<tr><td class="ps-4 fw-bold text-muted">${new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}</td><td><div class="d-flex align-items-center">${iconHtml}<span class="fw-semibold text-white">${speciesClean}</span></div></td><td><span class="badge bg-dark-subtle text-${d.confidence > 0.8 ? 'success' : 'warning'} border">${(d.confidence * 100).toFixed(0)}%</span></td><td><a href="${imgUrl}" target="_blank"><img src="${imgUrl}" class="table-img-preview" onerror="this.style.display='none'"></a></td><td class="text-end pe-4 text-muted font-monospace small">#${d.id}</td></tr>`;
    });
}

function updateChart(counts) {
    const canvas = document.getElementById('speciesChart');
    if (!canvas) return;
    // Destruir gráfica vieja si existe y estamos redibujando desde cero
    if (myChart) { myChart.destroy(); myChart = null; }

    const ctx = canvas.getContext('2d');
    const labels = Object.keys(counts).map(cleanName);
    const values = Object.values(counts);
    const natureColors = ['#2E7D32', '#C49A6C', '#0288D1', '#689F38', '#8D6E63'];

    myChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: labels, datasets: [{ data: values, backgroundColor: natureColors, borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#e0e0e0', font: {family: 'Roboto'} } } } }
    });
}

function safeSetText(id, text) { const el = document.getElementById(id); if (el) el.innerText = text; }
function cleanName(name) { if (!name) return "Desconocido"; let cleaned = name.split('_')[1] || name; return cleaned.charAt(0).toUpperCase() + cleaned.slice(1); }

// --- INICIALIZACIÓN ---
document.addEventListener('DOMContentLoaded', () => {
    // 1. Cargamos el HTML inicial del dashboard
    switchView('dashboard');
    // 2. Iniciamos el bucle de actualización
    setInterval(updateDashboard, 4000);
});