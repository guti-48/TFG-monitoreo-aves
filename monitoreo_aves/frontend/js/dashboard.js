const API_URL = "http://127.0.0.1:8000/detections/";

async function updateDashboard() {
    try {
        const response = await fetch(API_URL);
        
        // Si el servidor da error, lanzamos aviso
        if (!response.ok) {
            throw new Error(`Error Servidor: ${response.status}`);
        }
        
        const data = await response.json();
        
        // Si la lista está vacía (Aún no hay pájaros)
        if (data.length === 0) {
            document.getElementById('latest-detection-card').innerHTML = `
                <div class="card-body text-center p-5">
                    <h3 class="text-muted">Esperando primera detección...</h3>
                    <p>Asegúrate de que el nodo está grabando.</p>
                </div>
            `;
            return;
        }

        // Si hay datos, procesamos normal
        const sortedData = data.reverse();

        // Actualizar Contadores
        document.getElementById('total-counter').innerText = sortedData.length;
        const lastTime = new Date(sortedData[0].timestamp).toLocaleTimeString();
        document.getElementById('last-activity').innerText = lastTime;

        // Renderizar Última Detección
        renderLatestCard(sortedData[0]);

        // Renderizar Tabla
        renderHistoryTable(sortedData.slice(0, 10));

    } catch (error) {
        console.error("Error:", error);
        // Si hay error de conexión (CORS o Servidor apagado), LO MOSTRAMOS
        document.getElementById('latest-detection-card').innerHTML = `
            <div class="card-body text-center p-5">
                <h3 class="text-danger">Error de Conexión</h3>
                <p class="text-muted">${error.message}</p>
                <small>Abre la consola (F12) para más detalles.</small>
            </div>
        `;
    }
}

// Funciones auxiliares (se mantienen igual)
function cleanSpeciesName(rawName) {
    return rawName.split('_')[1] || rawName; 
}

function renderLatestCard(detection) {
    const container = document.getElementById('latest-detection-card');
    const percent = (detection.confidence * 100).toFixed(1);
    const species = cleanSpeciesName(detection.species);
    const date = new Date(detection.timestamp).toLocaleString();

    container.innerHTML = `
        <div class="card-body p-4 d-flex flex-column flex-md-row justify-content-between align-items-center">
            <div class="text-center text-md-start mb-3 mb-md-0">
                <h6 class="text-uppercase text-success fw-bold mb-1">Acaba de escucharse</h6>
                <h1 class="display-6 fw-bold text-dark mb-0"> ${species}</h1>
                <p class="text-muted mt-2 mb-0"><i class="bi bi-geo-alt"></i> ${detection.device_name} &bull; ${date}</p>
            </div>
            <div class="text-center">
                <div class="display-4 fw-bold text-success">${percent}%</div>
                <div class="text-muted small text-uppercase">Confianza</div>
            </div>
        </div>
    `;
}

function renderHistoryTable(detections) {
    const tbody = document.getElementById('history-table-body');
    tbody.innerHTML = ""; 

    detections.forEach(d => {
        const dateObj = new Date(d.timestamp);
        const time = dateObj.toLocaleTimeString();
        const percent = (d.confidence * 100).toFixed(1);
        const species = cleanSpeciesName(d.species);
        
        let badgeColor = "bg-secondary";
        if (d.confidence > 0.8) badgeColor = "bg-success";
        else if (d.confidence > 0.6) badgeColor = "bg-primary";
        else badgeColor = "bg-warning text-dark";

        const row = `
            <tr class="fade-in">
                <td class="ps-4 fw-bold text-muted">${time}</td>
                <td class="fw-bold text-dark">${species}</td>
                <td><span class="badge ${badgeColor} confidence-badge">${percent}%</span></td>
                <td>${d.device_name}</td>
                <td class="text-muted small text-truncate" style="max-width: 150px;">${d.filename}</td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

document.addEventListener('DOMContentLoaded', () => {
    updateDashboard();
    setInterval(updateDashboard, 3000);
});