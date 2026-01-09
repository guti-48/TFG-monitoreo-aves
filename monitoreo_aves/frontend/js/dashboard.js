const API_URL = "http://127.0.0.1:8000/detections/";
const IMG_BASE_URL = "http://127.0.0.1:8000/spectrograms/";

// --- CONFIGURACIÓN DE IMÁGENES ---
const ASSETS_PATH = 'assests/';
// Mapeo para ruidos conocidos que no son pájaros
const NOISE_MAP = {
    'Human vocal': 'human.jpg',
    'Motor': 'ruido_amb.png',
    // Añade aquí otros ruidos si aparecen
};
const PLACEHOLDER_IMG = ASSETS_PATH + 'placeholder.jpg';

let myChart = null;

async function updateDashboard() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error("API Backend desconectada");
        
        const data = await response.json();
        if (!data || data.length === 0) {
            console.log("Esperando datos..."); return;
        }

        const sortedData = data.reverse();
        const latest = sortedData[0];

        // 1. Actualizar KPIs (sin cambios)
        safeSetText('total-counter', sortedData.length);
        safeSetText('last-activity', new Date(latest.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}));
        
        const counts = {};
        sortedData.forEach(d => { counts[d.species] = (counts[d.species] || 0) + 1; });
        const topSpecies = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
        safeSetText('top-species', cleanName(topSpecies));

        // 2. Renderizar la TARJETA PRINCIPAL (con la magia de la foto)
        // Usamos await porque vamos a buscar la foto a internet
        await renderLiveFeedSplit(latest);

        // 3. Renderizar Tabla y Gráfica
        renderTable(sortedData.slice(0, 10));
        updateChart(counts);

    } catch (error) {
        console.error("Error Dashboard:", error);
        const container = document.getElementById('live-feed-container');
        if(container) container.innerHTML = `<div class="text-center text-danger py-5"><i class="bi bi-exclamation-triangle fs-1"></i><p>Error de conexión con el Backend</p></div>`;
    }
}

//PARA BUSCAR FOTO EN WIKIPEDIA 
async function getSpeciesImageUrl(speciesRawName) {
    // 1. Limpiamos el nombre (Quitamos guiones bajos y cosas raras)
    let clean = speciesRawName;
    if (speciesRawName.includes('_')) {
        clean = speciesRawName.split('_')[1];
    }
    clean = clean.replace(/-/g, ' ').trim();

    // 2. Si es ruido conocido (Humano/Motor), usar imagen local de assets
    if (NOISE_MAP[clean] || clean.includes("Human") || clean.includes("Motor")) {
        console.log("   -> Es ruido, usando imagen local.");
        if (clean.includes("Human")) return ASSETS_PATH + 'human.jpg';
        if (clean.includes("Motor")) return ASSETS_PATH + 'ruido_amb.png';
        return PLACEHOLDER_IMG;
    }

    // 3. Si es un pájaro, preguntar a Wikipedia
    try {
        const wikiUrl = `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(clean)}&prop=pageimages&format=json&pithumbsize=600&redirects=1&origin=*`;
        const res = await fetch(wikiUrl);
        const data = await res.json();
        
        const pages = data.query.pages;
        const pageId = Object.keys(pages)[0];

        // Si Wikipedia devuelve una página válida con foto (-1 significa que no encontró nada)
        if (pageId !== "-1" && pages[pageId].thumbnail) {
            const photoUrl = pages[pageId].thumbnail.source;
            console.log(`Foto encontrada en Wiki: ${photoUrl}`);
            return photoUrl;
        } else {
            console.warn(`Wikipedia no tiene foto para "${clean}"`);
        }
    } catch (e) {
        console.error("Error conectando con Wikipedia:", e);
    }

    // 4. Si todo falla, devuelve el pájaro genérico
    console.log("Usamos imagen por defecto.");
    return PLACEHOLDER_IMG;
}

async function renderLiveFeedSplit(d) {
    const container = document.getElementById('live-feed-container');
    if (!container) return;

    const species = cleanName(d.species);
    const percent = (d.confidence * 100).toFixed(0);
    const spectrogramUrl = `${IMG_BASE_URL}${d.filename.replace('.wav', '.png')}`;
    const timeStr = new Date(d.timestamp).toLocaleTimeString();

    // Estado de carga mientras buscamos la foto
    container.innerHTML = `<div class="d-flex justify-content-center align-items-center h-100"><div class="spinner-border text-success" role="status"></div></div>`;
    
    // BUSCAR LA FOTO 
    const speciesPhotoUrl = await getSpeciesImageUrl(d.species);

    // Inyectar el HTML del nuevo diseño
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
                    <div class="progress flex-grow-1" style="height: 8px; background-color: #333;">
                        <div class="progress-bar bg-success" role="progressbar" style="width: ${percent}%"></div>
                    </div>
                </div>

                <div class="spectrogram-container">
                    <img src="${spectrogramUrl}" class="img-fluid w-100" style="height: 120px; object-fit: cover; filter: contrast(1.2);" 
                         onerror="this.style.opacity='0.3';">
                    <div class="bg-dark text-muted small px-2 py-1 d-flex justify-content-between">
                        <span>Espectrograma de Audio</span>
                        <span class="font-monospace">${d.filename}</span>
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
        
        // Determinamos si es ruido o pájaro para el icono de la tabla
        let iconHtml = '<i class="bi bi-feather text-success me-2"></i>';
        if (NOISE_MAP[speciesClean]) {
             iconHtml = '<i class="bi bi-boombox text-muted me-2"></i>';
        }

        const row = `<tr>
            <td class="ps-4 fw-bold text-muted">${new Date(d.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'})}</td>
            <td>
                <div class="d-flex align-items-center">
                    ${iconHtml}
                    <span class="fw-semibold text-white">${speciesClean}</span>
                </div>
            </td>
            <td><span class="badge bg-dark-subtle text-${d.confidence > 0.8 ? 'success' : 'warning'} border">${(d.confidence * 100).toFixed(0)}%</span></td>
            <td><a href="${imgUrl}" target="_blank"><img src="${imgUrl}" class="table-img-preview" onerror="this.style.display='none'"></a></td>
            <td class="text-end pe-4 text-muted font-monospace small">#${d.id}</td>
        </tr>`;
        tbody.innerHTML += row;
    });
}

// Funciones auxiliares (Igual que antes)
function safeSetText(id, text) {
    const el = document.getElementById(id);
    if (el) el.innerText = text;
}
function cleanName(name) { 
    if (!name) return "Desconocido";
    let cleaned = name.split('_')[1] || name; 
    return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

function updateChart(counts) {
    const canvas = document.getElementById('speciesChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const labels = Object.keys(counts).map(cleanName);
    const values = Object.values(counts);

    const natureColors = ['#2E7D32', '#C49A6C', '#0288D1', '#689F38', '#8D6E63'];

    if (myChart) {
        myChart.data.labels = labels;
        myChart.data.datasets[0].data = values;
        myChart.update();
    } else {
        myChart = new Chart(ctx, {
            type: 'doughnut',
            data: { labels: labels, datasets: [{ data: values, backgroundColor: natureColors, borderWidth: 0 }] },
            options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: '#e0e0e0', font: {family: 'Roboto'} } } } }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    updateDashboard();
    // Actualizamos cada 4 segundos para dar tiempo a la API de Wikipedia
    setInterval(updateDashboard, 4000);
});