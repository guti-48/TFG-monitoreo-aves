const API_URL = "/detections/";
const DETECTION_REVIEW_BASE_URL = "/detections";
const SPECIES_OPTIONS_URL = "/species/options";
const IMG_BASE_URL = "/spectrograms/";
const ASSETS_PATH = 'assets/';
const NOISE_MAP = {
    'Human vocal': 'human.png',
    'Motor': 'ruido_amb.png',
};
const PLACEHOLDER_IMG = ASSETS_PATH + 'placeholder.jpg';

// HLS se consume por el proxy autenticado del backend. MediaMTX permanece
// accesible solo desde el propio servidor.
const BIRDMONITOR_CONFIG = window.BIRDMONITOR_CONFIG || {};
const DEFAULT_STREAM_NODE_NAME = BIRDMONITOR_CONFIG.streamNodeName || "birdmonitor";
const DEFAULT_STREAM_PATH = BIRDMONITOR_CONFIG.streamName || `${DEFAULT_STREAM_NODE_NAME}-audio`;
const MEDIAMTX_RTSP_PORT = BIRDMONITOR_CONFIG.mediaMtxRtspPort || 8554;
const LIVE_STREAM_BASE_URL = (
    BIRDMONITOR_CONFIG.liveStreamBaseUrl ||
    `${window.location.origin}/stream/hls`
).replace(/\/$/, "");
const LIVE_STREAM_RTSP_BASE_URL = (
    BIRDMONITOR_CONFIG.liveStreamRtspBaseUrl ||
    `rtsp://${window.location.hostname}:${MEDIAMTX_RTSP_PORT}`
).replace(/\/$/, "");
const STREAM_CONTROL_URL = "/stream/control";
let selectedStreamNodeName = DEFAULT_STREAM_NODE_NAME;
let selectedStreamPath = DEFAULT_STREAM_PATH;
let selectedStreamPathIsCustom = false;


let hlsInstance = null;
let hlsLibraryPromise = null;
let liveStreamSyncTimer = null;
let liveStreamVisibilityHandler = null;
let liveAudioContext = null;
let liveAnalyser = null;
let liveSourceNode = null;
let liveSourceAudio = null;
let liveSpectrumFrame = null;
let liveSpectrumData = null;
const LIVE_HLS_TARGET_SEGMENTS = 3;
const LIVE_HLS_MAX_SEGMENTS = 6;
const LIVE_NATIVE_EDGE_MARGIN_SECONDS = 1;

let currentView = 'dashboard';
let myChart = null;
let streamStatusTimer = null;
let lastStreamData = null;
let currentScienceReport = [];
let selectedScienceDeviceId = null;
const detectionCache = new Map();
const speciesPreviewCache = new Map();
const speciesChartColorMap = new Map();
const SPECIES_CHART_INITIAL_LIMIT = 7;
let latestSpeciesCounts = {};
let speciesChartExpanded = false;
let activeSpeciesPreviewTrigger = null;
let speciesPreviewHideTimer = null;
let detectionAudioReviewState = null;
let locationSites = [];
let locationDeployments = [];
let selectedSiteId = null;
let selectedDeploymentId = null;
let locationContextReady = false;
let locationChangeRequestId = 0;
let lastKnownActiveSiteId = null;
let locationCatalogRefreshInProgress = false;

function getSelectedSite() {
    return locationSites.find(site => Number(site.id) === Number(selectedSiteId)) || null;
}

function getActiveSite() {
    return locationSites.find(site => Number(site.active_deployment_count) > 0) || null;
}

function getSelectedDeployment() {
    return locationDeployments.find(
        deployment => Number(deployment.id) === Number(selectedDeploymentId)
    ) || null;
}

function locationLabel() {
    const site = getSelectedSite();
    return site?.name || 'Ubicación no seleccionada';
}

function locationFileToken() {
    const site = getSelectedSite();
    return String(site?.code || 'sin-ubicacion')
        .toLowerCase()
        .replace(/[^a-z0-9-]+/g, '-');
}

function locationScopeKey() {
    return `${selectedSiteId ?? 'none'}:${selectedDeploymentId ?? 'all'}`;
}

function locationAwareUrl(path, params = {}) {
    const numericSiteId = Number(selectedSiteId);
    if (
        !locationContextReady
        || selectedSiteId === null
        || !Number.isInteger(numericSiteId)
        || numericSiteId < 1
    ) {
        throw new Error('No hay una ubicación válida seleccionada');
    }

    const url = new URL(path, window.location.origin);
    url.searchParams.set('site_id', String(numericSiteId));
    const numericDeploymentId = Number(selectedDeploymentId);
    if (
        selectedDeploymentId !== null
        && Number.isInteger(numericDeploymentId)
        && numericDeploymentId > 0
    ) {
        url.searchParams.set('deployment_id', String(numericDeploymentId));
    }
    Object.entries(params).forEach(([key, value]) => {
        if (value !== null && value !== undefined && value !== '') {
            url.searchParams.set(key, String(value));
        }
    });
    return `${url.pathname}${url.search}`;
}

function formatDeploymentDate(value) {
    if (!value) return '';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return '';
    return parsed.toLocaleDateString('es-ES', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    });
}

async function fetchLocationDeployments(siteId) {
    const response = await fetch(`/sites/${encodeURIComponent(siteId)}/deployments`, {
        cache: 'no-store'
    });
    if (!response.ok) throw new Error(`HTTP ${response.status} al cargar campañas`);
    const deployments = await response.json();
    return Array.isArray(deployments) ? deployments : [];
}

function updateLocationControls() {
    const siteSelect = document.getElementById('location-site-select');
    const deploymentSelect = document.getElementById('location-deployment-select');
    const sidebarVersion = document.getElementById('sidebar-location-label');
    const selectedSite = getSelectedSite();

    if (siteSelect) {
        siteSelect.innerHTML = locationSites.map(site => {
            const activeSuffix = Number(site.active_deployment_count) > 0 ? ' · activa' : '';
            const shortName = site.municipality || site.name;
            return `<option value="${Number(site.id)}" ${Number(site.id) === Number(selectedSiteId) ? 'selected' : ''}>${escapeHtml(shortName)}${activeSuffix}</option>`;
        }).join('');
        siteSelect.disabled = locationSites.length < 2;
        siteSelect.title = selectedSite?.name || 'Ubicación seleccionada';
    }

    if (deploymentSelect) {
        const allLabel = 'Historial completo';
        deploymentSelect.innerHTML = `
            <option value="" ${selectedDeploymentId === null ? 'selected' : ''}>${allLabel}</option>
            ${locationDeployments.map(deployment => {
                const state = deployment.active ? 'Actual' : 'Finalizada';
                const period = deployment.active
                    ? `desde ${formatDeploymentDate(deployment.started_at)}`
                    : `${formatDeploymentDate(deployment.started_at)} – ${formatDeploymentDate(deployment.ended_at)}`;
                return `<option value="${Number(deployment.id)}" ${Number(deployment.id) === Number(selectedDeploymentId) ? 'selected' : ''}>${state} · ${period}</option>`;
            }).join('')}
        `;
        deploymentSelect.disabled = locationDeployments.length === 0;
    }

    const name = selectedSite?.name || 'Ubicación no disponible';
    if (sidebarVersion) sidebarVersion.textContent = `v2.2 · ${selectedSite?.municipality || name}`;
}

async function initializeLocationContext() {
    const response = await fetch(`/sites/?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status} al cargar ubicaciones`);

    const sites = await response.json();
    locationSites = Array.isArray(sites) ? sites : [];
    if (locationSites.length === 0) {
        throw new Error('No hay ubicaciones configuradas');
    }

    const activeSite = getActiveSite();
    selectedSiteId = Number((activeSite || locationSites[0]).id);
    lastKnownActiveSiteId = activeSite ? Number(activeSite.id) : null;
    selectedDeploymentId = null;
    locationDeployments = await fetchLocationDeployments(selectedSiteId);
    locationContextReady = true;
    updateLocationControls();
}

async function refreshLocationCatalog() {
    if (!locationContextReady || locationCatalogRefreshInProgress) return;
    locationCatalogRefreshInProgress = true;
    try {
        const response = await fetch(`/sites/?t=${Date.now()}`, {
            cache: 'no-store'
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const sites = await response.json();
        if (!Array.isArray(sites) || sites.length === 0) return;

        const previousActiveId = lastKnownActiveSiteId;
        locationSites = sites;
        const activeSite = getActiveSite();
        const activeId = activeSite ? Number(activeSite.id) : null;
        lastKnownActiveSiteId = activeId;

        if (
            activeId !== null
            && activeId !== previousActiveId
            && Number(selectedSiteId) === Number(previousActiveId)
        ) {
            const deployments = await fetchLocationDeployments(activeId);
            selectedSiteId = activeId;
            selectedDeploymentId = null;
            locationDeployments = deployments;
            resetLocationScopedState();
            updateLocationControls();
            refreshLocationScopedView();
            return;
        }
        updateLocationControls();
    } catch (error) {
        console.warn('No se pudo refrescar el catálogo de ubicaciones:', error);
    } finally {
        locationCatalogRefreshInProgress = false;
    }
}

function removeLocationSetupFlag() {
    const url = new URL(window.location.href);
    if (!url.searchParams.has('location_setup')) return;
    url.searchParams.delete('location_setup');
    window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
}

function closePhysicalLocationDialog() {
    document.getElementById('physical-location-dialog')?.remove();
    removeLocationSetupFlag();
}

function locationCommandStatusLabel(status) {
    return ({
        pending: 'Pendiente de recogida',
        delivered: 'Recibida por la Raspberry',
        applied: 'Aplicada',
        failed: 'Fallida',
        cancelled: 'Cancelada'
    })[status] || status;
}

async function getPrimaryNodeForLocationControl() {
    const devices = await fetchDevices();
    const activeDeployment = locationDeployments.find(item => item.active);
    return devices.find(item => item.name === 'birdmonitor')
        || devices.find(item => Number(item.id) === Number(activeDeployment?.device_id))
        || devices[0]
        || null;
}

async function fetchLocationCommands(deviceId) {
    const response = await fetch(
        `/devices/${encodeURIComponent(deviceId)}/location-commands?limit=10`,
        { cache: 'no-store' }
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const commands = await response.json();
    return Array.isArray(commands) ? commands : [];
}

async function openPhysicalLocationDialog(options = {}) {
    document.getElementById('physical-location-dialog')?.remove();
    const startup = options.startup === true;
    const dialog = document.createElement('div');
    dialog.id = 'physical-location-dialog';
    dialog.className = 'correction-dialog-backdrop';
    dialog.innerHTML = `
        <div class="correction-dialog" role="dialog" aria-modal="true" aria-labelledby="physical-location-title">
            <div class="correction-dialog-body text-center py-5">
                <div class="spinner-border text-success" role="status"></div>
                <p class="text-muted mt-3 mb-0">Consultando ubicación física del nodo...</p>
            </div>
        </div>`;
    document.body.appendChild(dialog);

    try {
        await refreshLocationCatalog();
        const node = await getPrimaryNodeForLocationControl();
        if (!node) throw new Error('No hay ningún nodo registrado');
        const commands = await fetchLocationCommands(node.id);
        const openCommand = commands.find(item => ['pending', 'delivered'].includes(item.status));
        const latestCommand = commands[0] || null;
        const activeSite = getActiveSite();
        const eligibleSites = locationSites.filter(
            site => Number.isFinite(Number(site.lat)) && Number.isFinite(Number(site.lon))
        );
        const selectedValue = openCommand?.target_site_id || activeSite?.id || eligibleSites[0]?.id || '';
        const statusBlock = openCommand
            ? `
                <div class="alert alert-warning mb-3">
                    <strong>${escapeHtml(locationCommandStatusLabel(openCommand.status))}:</strong>
                    cambio a ${escapeHtml(openCommand.target_site_name)}.
                    ${openCommand.status === 'pending'
                        ? 'La Raspberry todavía no ha recogido la orden.'
                        : 'La Raspberry ya la recibió y está terminando de aplicarla.'}
                </div>`
            : latestCommand
                ? `<div class="correction-empty-suggestion mb-3">Última orden: ${escapeHtml(locationCommandStatusLabel(latestCommand.status))} · ${escapeHtml(latestCommand.target_site_name)}</div>`
                : '';

        dialog.innerHTML = `
            <div class="correction-dialog" role="dialog" aria-modal="true" aria-labelledby="physical-location-title">
                <div class="correction-dialog-header">
                    <div>
                        <p class="correction-dialog-eyebrow">Configuración protegida del nodo</p>
                        <h3 id="physical-location-title">¿Dónde está instalada la Raspberry?</h3>
                    </div>
                    ${startup ? '' : `
                        <button type="button" class="correction-dialog-close" onclick="closePhysicalLocationDialog()" aria-label="Cerrar">
                            <i class="bi bi-x-lg"></i>
                        </button>`}
                </div>
                <div class="correction-dialog-body">
                    <div class="correction-original mb-3">
                        <span>Ubicación activa confirmada</span>
                        <strong>${escapeHtml(activeSite?.name || 'Sin ubicación activa')}</strong>
                    </div>
                    ${statusBlock}
                    ${eligibleSites.length === 0 ? `
                        <div class="alert alert-danger mb-3">
                            No hay ubicaciones con coordenadas válidas. Configura primero el catálogo de sitios.
                        </div>` : ''}
                    <label class="correction-field">
                        <span>Ubicación física real del nodo</span>
                        <select id="physical-location-site-select" class="form-select" ${openCommand ? 'disabled' : ''}>
                            ${eligibleSites.map(site => `
                                <option value="${Number(site.id)}" ${Number(site.id) === Number(selectedValue) ? 'selected' : ''}>
                                    ${escapeHtml(site.name)}${Number(site.active_deployment_count) > 0 ? ' · actual' : ''}
                                </option>`).join('')}
                        </select>
                    </label>
                    <label class="location-confirm-check mt-3 ${openCommand ? 'd-none' : ''}">
                        <input id="physical-location-confirm" type="checkbox">
                        <span>Confirmo que la caja ya está físicamente en el lugar seleccionado.</span>
                    </label>
                    <p class="correction-helper mt-3">
                        Consultar datos históricos no mueve el nodo. Esta acción crea una campaña nueva, actualiza las coordenadas de BirdNET y conserva los archivos pendientes en su ubicación anterior.
                    </p>
                    <div id="physical-location-feedback" aria-live="polite"></div>
                </div>
                <div class="correction-dialog-actions">
                    ${openCommand?.status === 'pending' ? `
                        <button type="button" class="btn btn-outline-danger" onclick="cancelPhysicalLocationCommand(${Number(node.id)}, ${Number(openCommand.id)})">
                            Cancelar orden pendiente
                        </button>` : ''}
                    <button type="button" class="btn btn-outline-secondary" onclick="closePhysicalLocationDialog()">
                        ${startup ? 'Mantener ubicación actual' : 'Cerrar'}
                    </button>
                    ${openCommand ? '' : `
                        <button type="button" class="btn btn-success" onclick="submitPhysicalLocationCommand(${Number(node.id)})" ${eligibleSites.length === 0 ? 'disabled' : ''}>
                            <i class="bi bi-send-check me-2"></i>Aplicar en la Raspberry
                        </button>`}
                </div>
            </div>`;
    } catch (error) {
        dialog.innerHTML = `
            <div class="correction-dialog" role="dialog" aria-modal="true">
                <div class="correction-dialog-body">
                    <div class="alert alert-danger mb-0">No se pudo cargar el control de ubicación: ${escapeHtml(error.message)}</div>
                </div>
                <div class="correction-dialog-actions">
                    <button type="button" class="btn btn-secondary" onclick="closePhysicalLocationDialog()">Cerrar</button>
                </div>
            </div>`;
    }
}

async function submitPhysicalLocationCommand(deviceId) {
    const siteSelect = document.getElementById('physical-location-site-select');
    const confirmation = document.getElementById('physical-location-confirm');
    const feedback = document.getElementById('physical-location-feedback');
    const site = locationSites.find(item => Number(item.id) === Number(siteSelect?.value));
    if (!site) return;

    const activeSite = getActiveSite();
    if (Number(site.id) === Number(activeSite?.id)) {
        closePhysicalLocationDialog();
        return;
    }
    if (!confirmation?.checked) {
        if (feedback) feedback.innerHTML = '<div class="alert alert-warning mt-3 mb-0">Debes confirmar que la Raspberry ya está físicamente en ese lugar.</div>';
        confirmation?.focus();
        return;
    }

    try {
        const response = await fetch(
            `/devices/${encodeURIComponent(deviceId)}/location-commands`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-BirdMonitor-CSRF': '1'
                },
                body: JSON.stringify({
                    target_site_id: Number(site.id),
                    confirm_site_code: site.code,
                    notes: 'Cambio confirmado desde el dashboard protegido'
                })
            }
        );
        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail.detail || `HTTP ${response.status}`);
        }
        const command = await response.json();
        if (feedback) {
            feedback.innerHTML = `
                <div class="alert alert-success mt-3 mb-0">
                    Orden creada para ${escapeHtml(command.target_site_name)}. Se aplicará en el próximo ciclo conectado de la Raspberry.
                </div>`;
        }
        window.setTimeout(() => openPhysicalLocationDialog(), 900);
    } catch (error) {
        if (feedback) feedback.innerHTML = `<div class="alert alert-danger mt-3 mb-0">${escapeHtml(error.message)}</div>`;
    }
}

async function cancelPhysicalLocationCommand(deviceId, commandId) {
    const feedback = document.getElementById('physical-location-feedback');
    try {
        const response = await fetch(
            `/devices/${encodeURIComponent(deviceId)}/location-commands/${encodeURIComponent(commandId)}/cancel`,
            {
                method: 'POST',
                headers: { 'X-BirdMonitor-CSRF': '1' }
            }
        );
        if (!response.ok) {
            const detail = await response.json().catch(() => ({}));
            throw new Error(detail.detail || `HTTP ${response.status}`);
        }
        await openPhysicalLocationDialog();
    } catch (error) {
        if (feedback) feedback.innerHTML = `<div class="alert alert-danger mt-3 mb-0">${escapeHtml(error.message)}</div>`;
    }
}

function resetLocationScopedState() {
    selectedScienceDeviceId = null;
    currentScienceReport = [];
    currentDailyData = [];
    detectionCache.clear();
    latestSpeciesCounts = {};
    speciesChartExpanded = false;
    if (myChart) {
        myChart.destroy();
        myChart = null;
    }
    if (dailyChartInst) {
        dailyChartInst.destroy();
        dailyChartInst = null;
    }
}

function refreshLocationScopedView() {
    const container = document.getElementById('main-content');
    if (!container) return;
    if (currentView === 'live') {
        renderLiveStreamView(container);
    } else {
        switchView(currentView);
    }
}

async function changeLocationSite(siteId) {
    const parsed = Number(siteId);
    if (!locationSites.some(site => Number(site.id) === parsed)) return;

    const requestId = ++locationChangeRequestId;
    try {
        const deployments = await fetchLocationDeployments(parsed);
        if (requestId !== locationChangeRequestId) return;

        selectedSiteId = parsed;
        selectedDeploymentId = null;
        locationDeployments = deployments;
        resetLocationScopedState();
        updateLocationControls();
        refreshLocationScopedView();
    } catch (error) {
        console.error('No se pudo cambiar la ubicación:', error);
        updateLocationControls();
        alert(`No se pudo cargar la ubicación seleccionada: ${error.message}`);
    }
}

function changeLocationDeployment(deploymentId) {
    const parsed = deploymentId === '' ? null : Number(deploymentId);
    if (parsed !== null && !locationDeployments.some(item => Number(item.id) === parsed)) {
        return;
    }

    selectedDeploymentId = parsed;
    resetLocationScopedState();
    updateLocationControls();
    refreshLocationScopedView();
}

function slugifyStreamValue(value) {
    const clean = String(value || '').trim().replace(/[^A-Za-z0-9_.-]+/g, '-').replace(/^-+|-+$/g, '');
    return clean || 'birdmonitor';
}

function normalizeStreamPath(value) {
    const clean = String(value || '').trim().replace(/^\/+|\/+$/g, '').replace(/[^A-Za-z0-9_./-]+/g, '-').replace(/\/+$/g, '');
    return clean || 'birdmonitor-audio';
}

function streamPathForNode(nodeName) {
    if (BIRDMONITOR_CONFIG.streamName && nodeName === DEFAULT_STREAM_NODE_NAME) {
        return normalizeStreamPath(BIRDMONITOR_CONFIG.streamName);
    }

    return `${slugifyStreamValue(nodeName)}-audio`;
}

function getCurrentHlsUrl() {
    if (!selectedStreamPathIsCustom && lastStreamData && lastStreamData.node_name === selectedStreamNodeName && lastStreamData.hls_url) {
        return lastStreamData.hls_url;
    }

    return `${LIVE_STREAM_BASE_URL}/${normalizeStreamPath(selectedStreamPath)}/index.m3u8`;
}

function getCurrentRtspUrl() {
    if (!selectedStreamPathIsCustom && lastStreamData && lastStreamData.node_name === selectedStreamNodeName && lastStreamData.rtsp_url) {
        return lastStreamData.rtsp_url;
    }

    return `${LIVE_STREAM_RTSP_BASE_URL}/${normalizeStreamPath(selectedStreamPath)}`;
}

function isAppleMobileDevice() {
    return /iPad|iPhone|iPod/.test(navigator.platform)
        || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

function shouldPrioritizeMobileAudio() {
    const coarsePointer = window.matchMedia
        && window.matchMedia('(pointer: coarse)').matches;
    return isAppleMobileDevice()
        || (navigator.maxTouchPoints > 0 && coarsePointer);
}

function ensureHlsLibrary() {
    if (window.Hls) return Promise.resolve(window.Hls);
    if (hlsLibraryPromise) return hlsLibraryPromise;

    hlsLibraryPromise = new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = new URL('./hls.min.js', getCurrentHlsUrl()).href;
        script.async = true;
        script.crossOrigin = 'anonymous';
        script.dataset.birdmonitorHlsFallback = 'true';

        script.onload = () => {
            if (!window.Hls) hlsLibraryPromise = null;
            resolve(window.Hls || null);
        };
        script.onerror = () => {
            script.remove();
            hlsLibraryPromise = null;
            resolve(null);
        };

        document.head.appendChild(script);
    });

    return hlsLibraryPromise;
}

async function fetchDevices() {
    const response = await fetch(`/devices/?t=${Date.now()}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const data = await response.json();
    return Array.isArray(data) ? data : [];
}

function updateLiveStreamLabels(data = null) {
    const streamPath = normalizeStreamPath((data && data.stream_path) || selectedStreamPath);
    const hlsUrl = (data && data.hls_url) || getCurrentHlsUrl();
    const rtspUrl = (data && data.rtsp_url) || getCurrentRtspUrl();

    const title = document.getElementById('live-stream-title');
    const hlsLabel = document.getElementById('live-hls-url');
    const clientHlsLabel = document.getElementById('live-client-hls-url');
    const rtspLabel = document.getElementById('live-rtsp-url');
    const pathInput = document.getElementById('live-stream-path-input');
    const nodeSelect = document.getElementById('live-node-select');

    if (title) title.textContent = streamPath;
    if (hlsLabel) hlsLabel.textContent = hlsUrl;
    if (clientHlsLabel) clientHlsLabel.textContent = hlsUrl;
    if (rtspLabel) rtspLabel.textContent = rtspUrl;
    if (pathInput && pathInput.value !== streamPath) pathInput.value = streamPath;
    if (nodeSelect && nodeSelect.value !== selectedStreamNodeName) nodeSelect.value = selectedStreamNodeName;
}

function cacheDetections(detections) {
    detections.forEach(detection => detectionCache.set(detection.id, detection));
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function renderSpeciesPreviewTrigger(speciesRawName, label) {
    const safeLabel = escapeHtml(label);

    if (!isSpeciesPreviewCandidate(speciesRawName, label)) {
        return `<span class="species-name-static">${safeLabel}</span>`;
    }

    const safeSpecies = escapeHtml(speciesRawName || label);

    return `
        <button
            type="button"
            class="species-preview-trigger"
            data-species="${safeSpecies}"
            onmouseenter="showSpeciesPreview(this)"
            onfocus="showSpeciesPreview(this)"
            onmouseleave="hideSpeciesPreview(this)"
            onblur="hideSpeciesPreview(this)"
            onclick="toggleSpeciesPreview(event, this)"
            aria-label="Ver vista previa de ${safeLabel}"
            aria-controls="species-preview-card"
            aria-expanded="false"
        >
            <span>${safeLabel}</span>
        </button>
    `;
}

function isSpeciesPreviewCandidate(speciesRawName, label) {
    const clean = cleanName(speciesRawName || label).trim();
    const normalized = clean.toLowerCase();
    const excludedNames = new Set(["desconocido", "unknown", "human vocal", "motor", "noise", "ruido"]);

    return Boolean(clean)
        && !NOISE_MAP[clean]
        && !excludedNames.has(normalized)
        && !normalized.includes("human")
        && !normalized.includes("motor")
        && !normalized.includes("noise")
        && !normalized.includes("ruido");
}

// NAVEGACIÓ
function switchView(viewName) {
    closeSpeciesPreview();
    closeDetectionAudioReview();

    if (currentView === 'live' && viewName !== 'live') {
        cleanupLiveStream();
    }

    currentView = viewName;

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
    const activeSite = getActiveSite();
    const liveScopeNotice = activeSite
        ? `La escucha en directo pertenece a la ubicación activa: <strong>${escapeHtml(activeSite.name)}</strong>.`
        : 'La escucha en directo pertenece al despliegue activo del nodo.';

    container.innerHTML = `
        <div class="row justify-content-center animate-fade-in">
            <div class="col-12 col-xl-9">
                <div class="alert alert-info small mb-3">
                    <i class="bi bi-broadcast-pin me-2"></i>${liveScopeNotice}
                    La selección histórica no modifica la fuente de audio en vivo.
                </div>
                <div class="card live-stream-card live-console">
                    <div class="card-body">
                        <div class="live-console-head">
                            <div class="live-stream-hero">
                                <div class="live-stream-icon">
                                    <i class="bi bi-soundwave"></i>
                                </div>
                                <div class="min-w-0">
                                    <p class="text-muted small text-uppercase fw-bold mb-1">Escucha en directo</p>
                                    <h4 class="fw-bold text-white mb-1"><span id="live-stream-title">${escapeHtml(selectedStreamPath)}</span></h4>
                                    <p class="text-muted mb-0 small">
                                        <span id="live-hls-url" class="font-monospace">${escapeHtml(getCurrentHlsUrl())}</span>
                                    </p>
                                </div>
                            </div>
                            <span id="live-stream-status" class="badge bg-secondary px-3 py-2">
                                <i class="bi bi-circle-fill me-1"></i>Consultando...
                            </span>
                        </div>

                        <div class="row g-2 mb-3">
                            <div class="col-md-6">
                                <label for="live-node-select" class="form-label text-muted small mb-1">Nodo</label>
                                <select id="live-node-select" class="form-select bg-dark text-white border-secondary" onchange="handleLiveNodeChange(this.value)">
                                    <option value="${escapeHtml(selectedStreamNodeName)}">${escapeHtml(selectedStreamNodeName)}</option>
                                </select>
                            </div>
                            <div class="col-md-6">
                                <label for="live-stream-path-input" class="form-label text-muted small mb-1">Path MediaMTX</label>
                                <input id="live-stream-path-input" class="form-control bg-dark text-white border-secondary" value="${escapeHtml(selectedStreamPath)}" onchange="handleLiveStreamPathChange(this.value)">
                            </div>
                        </div>

                        <div class="live-client-access">
                            <div class="live-client-access-item">
                                <span><i class="bi bi-phone me-1"></i>Navegador móvil · HLS</span>
                                <code id="live-client-hls-url">${escapeHtml(getCurrentHlsUrl())}</code>
                            </div>
                            <div class="live-client-access-item">
                                <span><i class="bi bi-display me-1"></i>VLC · RTSP</span>
                                <code id="live-rtsp-url">${escapeHtml(getCurrentRtspUrl())}</code>
                            </div>
                        </div>

                        <div class="live-player-shell">
                            <div class="audio-panel live-audio-panel">
                                <audio id="live-audio-player" class="w-100" controls preload="none" playsinline crossorigin="anonymous"></audio>
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
                                <i class="bi bi-broadcast me-2"></i>Iniciar emisión
                            </button>
                            <button class="btn btn-outline-info" onclick="initLiveStreamPlayer(true)">
                                <i class="bi bi-headphones me-2"></i>Escuchar en este dispositivo
                            </button>
                            <button class="btn btn-outline-secondary" onclick="stopLiveStreamPlayer()">
                                <i class="bi bi-stop-circle me-2"></i>Desconectar este dispositivo
                            </button>
                            <button class="btn btn-outline-primary" onclick="copyLiveStreamUrl('rtsp')">
                                <i class="bi bi-clipboard me-2"></i>Copiar URL para VLC
                            </button>
                        </div>

                        <p id="live-stream-message" class="text-muted small mb-0 mt-3">
                            Inicia la emisión si está detenida y después conecta este reproductor.
                        </p>

                        <div class="live-mini-note">
                            La Raspberry publica una sola señal. El servidor la distribuye a todos los móviles,
                            navegadores y VLC conectados; desconectar este dispositivo no afecta a los demás.
                        </div>

                        <details class="live-global-control">
                            <summary>Control global de la estación</summary>
                            <p>Esta acción corta el directo para todos los dispositivos conectados.</p>
                            <button class="btn btn-sm btn-outline-danger" onclick="stopLiveStationForAll()">
                                <i class="bi bi-power me-2"></i>Detener emisión para todos
                            </button>
                        </details>
                    </div>
                </div>
            </div>
        </div>`;

    populateLiveNodeSelector().finally(() => refreshLiveStreamControlStatus());
    if (!isAppleMobileDevice()) ensureHlsLibrary();

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

async function populateLiveNodeSelector() {
    const select = document.getElementById('live-node-select');
    if (!select) return;

    try {
        const devices = await fetchDevices();
        const names = devices
            .map(device => String(device.name || '').trim())
            .filter(Boolean);

        if (!BIRDMONITOR_CONFIG.streamNodeName && names.length > 0 && !names.includes(selectedStreamNodeName)) {
            selectedStreamNodeName = names[0];
            selectedStreamPath = streamPathForNode(selectedStreamNodeName);
            selectedStreamPathIsCustom = false;
            lastStreamData = null;
        }

        const options = [...new Set([selectedStreamNodeName, ...names])];
        select.innerHTML = options
            .map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
            .join('');
        select.value = selectedStreamNodeName;
        updateLiveStreamLabels();
    } catch (e) {
        setLiveStreamMessage(`No se pudieron cargar los nodos registrados: ${e.message}`, true);
    }
}

function handleLiveNodeChange(nodeName) {
    selectedStreamNodeName = String(nodeName || DEFAULT_STREAM_NODE_NAME).trim() || DEFAULT_STREAM_NODE_NAME;
    selectedStreamPath = streamPathForNode(selectedStreamNodeName);
    selectedStreamPathIsCustom = false;
    lastStreamData = null;
    stopLiveStreamPlayer();
    updateLiveStreamLabels();
    refreshLiveStreamControlStatus();
}

function handleLiveStreamPathChange(streamPath) {
    selectedStreamPath = normalizeStreamPath(streamPath);
    selectedStreamPathIsCustom = true;
    lastStreamData = null;
    stopLiveStreamPlayer();
    updateLiveStreamLabels();
}

async function fetchLiveStreamControlStatus() {
    const response = await fetch(
        `${STREAM_CONTROL_URL}?node_name=${encodeURIComponent(selectedStreamNodeName)}&t=${Date.now()}`,
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

        if (data.node_name) selectedStreamNodeName = data.node_name;
        if (data.stream_path && !selectedStreamPathIsCustom) {
            selectedStreamPath = normalizeStreamPath(data.stream_path);
        }

        const hlsUrl = selectedStreamPathIsCustom ? getCurrentHlsUrl() : (data.hls_url || getCurrentHlsUrl());
        updateLiveStreamLabels(selectedStreamPathIsCustom ? null : data);

        const hlsLabel = document.getElementById('live-hls-url');

        if (hlsLabel) hlsLabel.textContent = hlsUrl;

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
            headers: {
                'Content-Type': 'application/json',
                'X-BirdMonitor-CSRF': '1'
            },
            body: JSON.stringify({
                node_name: selectedStreamNodeName,
                stream_enabled: enabled,
                stream_path: selectedStreamPath
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        lastStreamData = await response.json();
        selectedStreamPathIsCustom = false;
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

function stopLiveStationForAll() {
    const confirmed = window.confirm(
        'Esta acción detendrá la emisión en la Raspberry y desconectará a todos los oyentes. ¿Quieres continuar?'
    );

    if (confirmed) setLiveStreamEnabled(false);
}

async function copyLiveStreamUrl(kind) {
    const url = kind === 'rtsp' ? getCurrentRtspUrl() : getCurrentHlsUrl();

    try {
        await navigator.clipboard.writeText(url);
        setLiveStreamMessage(kind === 'rtsp'
            ? 'URL RTSP copiada. En VLC usa Medio → Abrir ubicación de red.'
            : 'URL HLS copiada.'
        );
    } catch (_) {
        window.prompt('Copia esta URL:', url);
    }
}

function getLiveLatencySeconds(audio) {
    if (
        hlsInstance
        && Number.isFinite(hlsInstance.latency)
        && hlsInstance.latency >= 0
    ) {
        return hlsInstance.latency;
    }

    if (audio && audio.seekable && audio.seekable.length > 0) {
        const liveEdge = audio.seekable.end(audio.seekable.length - 1);
        if (Number.isFinite(liveEdge) && Number.isFinite(audio.currentTime)) {
            return Math.max(0, liveEdge - audio.currentTime);
        }
    }

    return null;
}

function moveLivePlayerToEdge(audio, force = false) {
    if (!audio) return false;

    const latency = getLiveLatencySeconds(audio);
    if (!force && (latency === null || latency <= LIVE_HLS_MAX_SEGMENTS)) {
        return false;
    }

    let target = null;
    if (hlsInstance && Number.isFinite(hlsInstance.liveSyncPosition)) {
        target = hlsInstance.liveSyncPosition;
    } else if (audio.seekable && audio.seekable.length > 0) {
        const rangeIndex = audio.seekable.length - 1;
        const rangeStart = audio.seekable.start(rangeIndex);
        const rangeEnd = audio.seekable.end(rangeIndex);
        target = Math.max(
            rangeStart,
            rangeEnd - LIVE_NATIVE_EDGE_MARGIN_SECONDS
        );
    }

    if (!Number.isFinite(target)) return false;

    try {
        if (Math.abs(audio.currentTime - target) > 0.25) {
            audio.currentTime = target;
        }
        return true;
    } catch (_) {
        return false;
    }
}

function detachLiveSynchronization() {
    if (liveStreamSyncTimer) {
        clearInterval(liveStreamSyncTimer);
        liveStreamSyncTimer = null;
    }

    if (liveStreamVisibilityHandler) {
        document.removeEventListener('visibilitychange', liveStreamVisibilityHandler);
        liveStreamVisibilityHandler = null;
    }
}

function attachLiveSynchronization(audio) {
    detachLiveSynchronization();

    liveStreamVisibilityHandler = () => {
        if (document.visibilityState !== 'visible' || audio.paused) return;

        if (liveAudioContext && liveAudioContext.state === 'suspended') {
            liveAudioContext.resume().catch(() => {});
        }

        moveLivePlayerToEdge(audio, true);
    };
    document.addEventListener('visibilitychange', liveStreamVisibilityHandler);

    liveStreamSyncTimer = setInterval(() => {
        if (!audio.paused) moveLivePlayerToEdge(audio);
    }, 3000);
}

async function initLiveStreamPlayer(autoplay = false) {
    const audio = document.getElementById('live-audio-player');
    if (!audio) return;

    detachLiveSynchronization();
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    audio.crossOrigin = 'anonymous';
    audio.onplay = () => {
        moveLivePlayerToEdge(audio, true);
        startLiveSpectrum(audio);
    };
    audio.onplaying = () => setLiveStreamStatus('online', 'En directo');
    audio.onpause = () => setLiveSpectrumState('Pausado');
    audio.onwaiting = () => {
        setTimeout(() => moveLivePlayerToEdge(audio), 500);
    };
    audio.onstalled = () => {
        setTimeout(() => moveLivePlayerToEdge(audio), 500);
    };
    audio.onerror = null;
    audio.onloadedmetadata = null;
    attachLiveSynchronization(audio);

    if (hlsInstance) {
        hlsInstance.destroy();
        hlsInstance = null;
    }

    const hlsUrl = getCurrentHlsUrl();

    setLiveStreamStatus('checking', 'Conectando...');
    setLiveStreamMessage('Conectando con el flujo HLS protegido...');

    const attachNativeHls = () => {
        audio.src = hlsUrl;
        audio.load();
        audio.onloadedmetadata = () => {
            setLiveStreamStatus('online', 'Stream disponible');
            setLiveStreamMessage('Stream cargado mediante HLS nativo.');
            moveLivePlayerToEdge(audio, true);
        };
        audio.onerror = () => {
            setLiveStreamStatus('offline', 'Stream no disponible');
            setLiveStreamMessage('El navegador no pudo abrir el HLS protegido. Recarga la sesión e inténtalo de nuevo.', true);
        };

        if (autoplay) {
            audio.play().catch(() => {
                setLiveStreamMessage('Pulsa play para comenzar: el móvil bloqueó la reproducción automática.');
            });
        }
    };

    if (isAppleMobileDevice() && audio.canPlayType('application/vnd.apple.mpegurl')) {
        attachNativeHls();
        return;
    }

    const HlsPlayer = window.Hls || await ensureHlsLibrary();
    if (document.getElementById('live-audio-player') !== audio) return;

    if (HlsPlayer && HlsPlayer.isSupported()) {
        hlsInstance = new HlsPlayer({
            enableWorker: true,
            lowLatencyMode: false,
            liveSyncDurationCount: LIVE_HLS_TARGET_SEGMENTS,
            liveMaxLatencyDurationCount: LIVE_HLS_MAX_SEGMENTS,
            maxLiveSyncPlaybackRate: 1.25,
            maxBufferLength: 8,
            maxMaxBufferLength: 12,
            backBufferLength: 10
        });

        hlsInstance.on(HlsPlayer.Events.MEDIA_ATTACHED, () => {
            if (hlsInstance) hlsInstance.loadSource(hlsUrl);
        });

        hlsInstance.on(HlsPlayer.Events.MANIFEST_PARSED, () => {
            setLiveStreamStatus('online', 'Stream disponible');
            setLiveStreamMessage('Stream cargado cerca del borde en directo.');
            if (autoplay) {
                audio.play().catch(() => {
                    setLiveStreamMessage('El navegador bloqueó la reproducción automática. Pulsa play manualmente.');
                });
            }
        });

        hlsInstance.on(HlsPlayer.Events.ERROR, (_, data) => {
            if (!data || !data.fatal) return;

            if (data.type === HlsPlayer.ErrorTypes.NETWORK_ERROR && hlsInstance) {
                setLiveStreamStatus('warning', 'Reconectando...');
                setLiveStreamMessage('Se perdió la conexión con el directo. Reintentando...');
                hlsInstance.startLoad();
                return;
            }

            if (data.type === HlsPlayer.ErrorTypes.MEDIA_ERROR && hlsInstance) {
                setLiveStreamStatus('warning', 'Recuperando audio...');
                hlsInstance.recoverMediaError();
                return;
            }

            setLiveStreamStatus('offline', 'Stream no disponible');
            setLiveStreamMessage('No se pudo cargar el HLS protegido. Comprueba la red y la sesión.', true);

            if (hlsInstance) hlsInstance.destroy();
            hlsInstance = null;
        });

        hlsInstance.attachMedia(audio);
        return;
    }

    if (audio.canPlayType('application/vnd.apple.mpegurl')) {
        attachNativeHls();
        return;
    }

    setLiveStreamStatus('warning', 'HLS no soportado');
    setLiveStreamMessage('Este navegador no soporta HLS integrado.', true);
}

function setLiveSpectrumState(text) {
    const el = document.getElementById('live-spectrum-state');
    if (el) el.textContent = text;
}

async function startLiveSpectrum(audio) {
    const canvas = document.getElementById('live-spectrum-canvas');
    if (!canvas || !audio) return;

    if (shouldPrioritizeMobileAudio()) {
        setLiveSpectrumState('Audio prioritario en móvil');
        return;
    }

    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) {
            setLiveSpectrumState('No soportado');
            return;
        }

        if (!liveAudioContext) {
            liveAudioContext = new AudioCtx();
        }

        if (liveAudioContext.state !== 'running') {
            await liveAudioContext.resume();
        }

        if (liveAudioContext.state !== 'running') {
            setLiveSpectrumState('Sin visualización');
            return;
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

    detachLiveSynchronization();
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

function getReviewStatus(detection) {
    return detection.review?.status || "unreviewed";
}

function getReviewMeta(status) {
    const map = {
        unreviewed: {
            label: "Sin revisar",
            badge: "review-badge-unreviewed",
            icon: "bi-hourglass-split"
        },
        validated: {
            label: "Validada",
            badge: "review-badge-validated",
            icon: "bi-check-circle-fill"
        },
        corrected: {
            label: "Corregida",
            badge: "review-badge-corrected",
            icon: "bi-pencil-square"
        },
        noise: {
            label: "Ruido",
            badge: "review-badge-noise",
            icon: "bi-volume-mute-fill"
        },
        doubtful: {
            label: "Dudosa",
            badge: "review-badge-doubtful",
            icon: "bi-question-circle-fill"
        },
        discarded: {
            label: "Descartada",
            badge: "review-badge-discarded",
            icon: "bi-x-circle-fill"
        }
    };

    return map[status] || map.unreviewed;
}

function getDisplaySpecies(detection) {
    if (detection.review?.status === "noise") {
        return "Ruido ambiente";
    }

    if (detection.review?.status === "corrected" && detection.review.corrected_species) {
        return detection.review.corrected_species;
    }

    return detection.species;
}

function getLearningSuggestion(detection) {
    if (getReviewStatus(detection) !== "unreviewed") return null;
    return detection.learned_suggestion || null;
}

function getLearningSuggestionLabel(suggestion) {
    if (!suggestion) return "";
    if (suggestion.status === "noise") return "Ruido ambiente";
    if (suggestion.status === "discarded") return "Descartar registro";
    return cleanName(suggestion.effective_species || suggestion.corrected_species || suggestion.status);
}

function buildLearningSuggestionBadge(detection) {
    const suggestion = getLearningSuggestion(detection);
    if (!suggestion) return "";

    const label = getLearningSuggestionLabel(suggestion);
    const confidence = Math.round((suggestion.learning_confidence || 0) * 100);

    return `
        <div class="learning-suggestion-badge mt-1">
            <i class="bi bi-stars me-1"></i>
            Sugerencia: ${label}
            <span>${suggestion.support_count} revisiones - ${confidence}%</span>
        </div>
    `;
}

function buildLearningSuggestionPanel(detection) {
    const suggestion = getLearningSuggestion(detection);
    if (!suggestion) return "";

    const label = getLearningSuggestionLabel(suggestion);

    return `
        <div class="learning-suggestion-panel">
            <div>
                <span class="learning-suggestion-title">
                    <i class="bi bi-stars me-1"></i>Sugerencia aprendida
                </span>
                <p class="mb-0 small">
                    El sistema propone <strong>${label}</strong> porque ya hay ${suggestion.support_count} revisiones humanas parecidas.
                </p>
            </div>
            <button class="btn btn-sm btn-success" onclick="applyLearnedSuggestion(${detection.id})">
                Aplicar
            </button>
        </div>
    `;
}

function buildReviewBadge(detection) {
    const status = getReviewStatus(detection);
    const meta = getReviewMeta(status);

    let extra = "";

    if (status === "corrected" && detection.review?.corrected_species) {
        extra = ` → ${cleanName(detection.review.corrected_species)}`;
    }

    return `
        <span class="badge review-badge ${meta.badge}">
            <i class="bi ${meta.icon} me-1"></i>${meta.label}${extra}
        </span>
    `;
}

function buildReviewActions(detection) {
    const suggestion = getLearningSuggestion(detection);
    const suggestionAction = suggestion ? `
            <button class="btn btn-outline-success review-action-suggestion" title="Aplicar sugerencia aprendida" onclick="applyLearnedSuggestion(${detection.id})">
                <i class="bi bi-stars"></i>
            </button>
    ` : "";

    return `
        <div class="btn-group btn-group-sm review-actions" role="group" aria-label="Revision deteccion ${detection.id}">
            ${suggestionAction}
            <button class="btn btn-outline-success" title="Validar deteccion" onclick="quickReviewDetection(${detection.id}, 'validated')">
                <i class="bi bi-check-lg"></i>
            </button>
            <button class="btn btn-outline-warning" title="Marcar como ruido" onclick="quickReviewDetection(${detection.id}, 'noise')">
                <i class="bi bi-volume-mute"></i>
            </button>
            <button class="btn btn-outline-info" title="Corregir especie" onclick="correctDetectionSpecies(${detection.id})">
                <i class="bi bi-pencil"></i>
            </button>
            <button class="btn btn-outline-primary" title="Marcar como dudosa" onclick="quickReviewDetection(${detection.id}, 'doubtful')">
                <i class="bi bi-question-lg"></i>
            </button>
            <button class="btn btn-outline-danger" title="Descartar deteccion" onclick="quickReviewDetection(${detection.id}, 'discarded')">
                <i class="bi bi-x-lg"></i>
            </button>
        </div>
    `;
}

function buildAudioEvidenceButton(detection, imageUrl = null) {
    const safeSpecies = escapeHtml(cleanName(getDisplaySpecies(detection)));

    if (imageUrl) {
        return `
            <button
                type="button"
                class="audio-evidence-thumbnail"
                title="Escuchar y revisar la evidencia de ${safeSpecies}"
                aria-label="Escuchar y revisar la evidencia de ${safeSpecies}"
                onclick="openDetectionAudioReview(${detection.id})"
            >
                <img src="${escapeHtml(imageUrl)}" alt="" onerror="this.style.visibility='hidden'">
                <span class="audio-evidence-thumbnail-icon" aria-hidden="true">
                    <i class="bi bi-play-fill"></i>
                </span>
            </button>
        `;
    }

    return `
        <button
            type="button"
            class="btn btn-sm audio-evidence-open"
            title="Escuchar y revisar la evidencia de ${safeSpecies}"
            onclick="openDetectionAudioReview(${detection.id})"
        >
            <i class="bi bi-soundwave" aria-hidden="true"></i>
            <span>Escuchar</span>
        </button>
    `;
}

function formatAudioReviewTime(seconds) {
    const safeSeconds = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safeSeconds / 60);
    const remainder = Math.floor(safeSeconds % 60);
    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function formatSignedAudioDb(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return "--";
    return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(1)} dB`;
}

function renderAudioReviewDiagnostics(diagnostics) {
    if (!diagnostics) return "";

    const requiresReview = diagnostics.status === "review";
    const lowFrequencyPercent = Math.round(
        Math.min(1, Math.max(0, Number(diagnostics.low_frequency_ratio) || 0)) * 100,
    );
    const humProminence = formatSignedAudioDb(diagnostics.mains_hum_prominence_db);
    const birdSnr = diagnostics.bird_band_snr_db == null
        ? null
        : formatSignedAudioDb(diagnostics.bird_band_snr_db);

    return `
        <details class="audio-review-diagnostics ${requiresReview ? "needs-review" : "is-ok"}">
            <summary class="audio-review-diagnostics-head">
                <span class="audio-review-diagnostics-status">
                    <i class="bi ${requiresReview ? "bi-exclamation-triangle" : "bi-check-circle"}" aria-hidden="true"></i>
                    <span>
                        <strong>Calidad del audio</strong>
                        <small>${requiresReview ? "Conviene escuchar antes de validar" : "Sin avisos relevantes"}</small>
                    </span>
                </span>
                <span class="audio-review-diagnostics-toggle">
                    Detalles tecnicos
                    <i class="bi bi-chevron-down" aria-hidden="true"></i>
                </span>
            </summary>
            <div class="audio-review-diagnostics-body">
                <p>${escapeHtml(diagnostics.summary || "")}</p>
                <div class="audio-review-diagnostic-values">
                    <span title="Porcentaje de energia por debajo de 200 Hz">
                        Graves <strong>${lowFrequencyPercent}%</strong>
                    </span>
                    <span title="Prominencia maxima de 50, 100, 150 o 200 Hz">
                        Zumbido <strong>${humProminence}</strong>
                    </span>
                    ${birdSnr === null ? "" : `
                        <span title="Energia de 1,2 a 10 kHz dentro de la ventana frente al fondo">
                            Contraste <strong>${birdSnr}</strong>
                        </span>
                    `}
                </div>
            </div>
        </details>
    `;
}

async function openDetectionAudioReview(detectionId) {
    closeSpeciesPreview();
    closeDetectionAudioReview();

    const detection = detectionCache.get(detectionId);
    const species = cleanName(getDisplaySpecies(detection || { species: "Deteccion" }));
    const dialog = document.createElement("div");
    dialog.id = "audio-review-dialog";
    dialog.className = "audio-review-backdrop";
    dialog.innerHTML = `
        <section class="audio-review-dialog" role="dialog" aria-modal="true" aria-labelledby="audio-review-title">
            <header class="audio-review-header">
                <div>
                    <p class="audio-review-eyebrow">Evidencia acustica</p>
                    <h3 id="audio-review-title">${escapeHtml(species)}</h3>
                </div>
                <button type="button" class="audio-review-close" onclick="closeDetectionAudioReview()" title="Cerrar" aria-label="Cerrar">
                    <i class="bi bi-x-lg"></i>
                </button>
            </header>
            <div id="audio-review-content" class="audio-review-loading" aria-live="polite">
                <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
                <span>Preparando el tramo de audio...</span>
            </div>
        </section>
    `;

    dialog.addEventListener("click", event => {
        if (event.target === dialog) closeDetectionAudioReview();
    });
    document.body.appendChild(dialog);

    try {
        const response = await fetch(`/detections/${detectionId}/review-media`, { cache: "no-store" });
        if (!response.ok) {
            const errorPayload = await response.json().catch(() => ({}));
            throw new Error(errorPayload.detail || `HTTP ${response.status}`);
        }

        const media = await response.json();
        if (!document.body.contains(dialog)) return;
        renderDetectionAudioReview(detectionId, detection, media);
    } catch (error) {
        const content = document.getElementById("audio-review-content");
        if (content) {
            content.className = "audio-review-error";
            content.innerHTML = `
                <i class="bi bi-exclamation-circle" aria-hidden="true"></i>
                <div>
                    <strong>No se pudo abrir la evidencia de audio</strong>
                    <span>${escapeHtml(error.message)}</span>
                </div>
            `;
        }
    }
}

function renderDetectionAudioReview(detectionId, detection, media) {
    const content = document.getElementById("audio-review-content");
    if (!content) return;

    const reviewStart = Number(media.review_start_seconds) || 0;
    const reviewEnd = Number(media.review_end_seconds) || reviewStart;
    const reviewDuration = Math.max(0.001, reviewEnd - reviewStart);
    const detectionStart = Number(media.audio_start_seconds);
    const detectionEnd = Number(media.audio_end_seconds);
    const hasTiming = media.timing_available
        && Number.isFinite(detectionStart)
        && Number.isFinite(detectionEnd);
    const markerStart = hasTiming ? Math.max(reviewStart, detectionStart) : reviewStart;
    const markerEnd = hasTiming ? Math.min(reviewEnd, detectionEnd) : reviewStart;
    const markerLeft = ((markerStart - reviewStart) / reviewDuration) * 100;
    const markerWidth = Math.max(0, ((markerEnd - markerStart) / reviewDuration) * 100);
    const ticks = [0, 0.25, 0.5, 0.75, 1]
        .map(position => `
            <span style="left:${position * 100}%">
                ${formatAudioReviewTime(reviewStart + reviewDuration * position)}
            </span>
        `)
        .join("");
    const confidence = detection ? `${Math.round((detection.confidence || 0) * 100)}%` : "--";

    content.className = "audio-review-content";
    content.innerHTML = `
        <div class="audio-review-summary" aria-label="Resumen de la deteccion">
            <span>BirdNET <strong>${confidence}</strong></span>
            <span class="audio-review-summary-separator" aria-hidden="true">&middot;</span>
            <span>
                ${hasTiming
                    ? `Evento <strong>${formatAudioReviewTime(detectionStart)} - ${formatAudioReviewTime(detectionEnd)}</strong>`
                    : `Contexto <strong>${formatAudioReviewTime(reviewStart)} - ${formatAudioReviewTime(reviewEnd)}</strong>`}
            </span>
        </div>

        <div class="audio-review-spectrum-layout">
            <div class="audio-review-frequency-axis" aria-hidden="true">
                <span>10 kHz</span>
                <span>5 kHz</span>
                <span>0,25 kHz</span>
            </div>
            <div class="audio-review-spectrum-column">
                <div
                    id="audio-review-plot"
                    class="audio-review-plot"
                    role="slider"
                    tabindex="0"
                    aria-label="Posicion de reproduccion sobre el espectrograma"
                    aria-valuemin="0"
                    aria-valuemax="${reviewDuration.toFixed(2)}"
                    aria-valuenow="0"
                    onclick="seekDetectionAudioReview(event)"
                    onkeydown="handleDetectionAudioReviewKey(event)"
                >
                    <span class="audio-review-image-loading">Generando espectrograma...</span>
                    <img
                        src="${escapeHtml(media.spectrogram_url)}"
                        alt="Espectrograma del tramo de comprobacion"
                        draggable="false"
                        onload="markDetectionSpectrogramReady()"
                        onerror="markDetectionSpectrogramError()"
                    >
                    ${hasTiming ? `
                        <span
                            class="audio-review-detection-window"
                            style="left:${markerLeft}%;width:${markerWidth}%"
                            aria-hidden="true"
                        ></span>
                    ` : ""}
                    <span id="audio-review-playhead" class="audio-review-playhead" aria-hidden="true"></span>
                </div>
                <div class="audio-review-time-axis" aria-hidden="true">${ticks}</div>
            </div>
        </div>

        <div class="audio-review-legend">
            <div>
                ${hasTiming ? `
                    <span><i class="audio-review-marker-swatch" aria-hidden="true"></i>Zona clasificada por BirdNET</span>
                ` : `
                    <span class="audio-review-legacy-note"><i class="bi bi-info-circle" aria-hidden="true"></i>Este registro no conserva la marca temporal de BirdNET; se muestran sus primeros 20 segundos.</span>
                `}
            </div>
        </div>

        <div class="audio-review-controls">
            <button id="audio-review-play" type="button" class="audio-review-play" onclick="toggleDetectionAudioReview()" title="Reproducir" aria-label="Reproducir">
                <i class="bi bi-play-fill"></i>
            </button>
            <button type="button" class="audio-review-control-icon" onclick="resetDetectionAudioReview()" title="Volver al inicio" aria-label="Volver al inicio">
                <i class="bi bi-skip-start-fill"></i>
            </button>
            <output id="audio-review-clock" class="audio-review-clock">00:00 / ${formatAudioReviewTime(reviewDuration)}</output>
            <div class="audio-review-volume">
                <button id="audio-review-mute" type="button" class="audio-review-control-icon" onclick="toggleDetectionAudioMute()" title="Silenciar" aria-label="Silenciar">
                    <i class="bi bi-volume-up-fill"></i>
                </button>
                <input type="range" min="0" max="1" step="0.05" value="1" aria-label="Volumen" oninput="setDetectionAudioVolume(this.value)">
            </div>
        </div>

        ${renderAudioReviewDiagnostics(media.diagnostics)}

        <footer class="audio-review-footer">
            <div>
                <span class="audio-review-footer-label">Revision humana</span>
                ${detection ? buildReviewBadge(detection) : ""}
            </div>
            ${detection ? buildReviewActions(detection) : ""}
        </footer>

        <audio id="audio-review-engine" preload="metadata" src="${escapeHtml(media.audio_url)}"></audio>
    `;

    initializeDetectionAudioReview(media);
}

function initializeDetectionAudioReview(media) {
    const audio = document.getElementById("audio-review-engine");
    if (!audio) return;

    detectionAudioReviewState = {
        audio,
        start: Number(media.review_start_seconds) || 0,
        end: Number(media.review_end_seconds) || 0,
        frame: null,
        finished: false,
    };

    audio.addEventListener("loadedmetadata", () => {
        const state = detectionAudioReviewState;
        if (!state || state.audio !== audio) return;
        audio.currentTime = state.start;
        updateDetectionAudioReviewPlayback();
    });
    audio.addEventListener("timeupdate", updateDetectionAudioReviewPlayback);
    audio.addEventListener("play", () => {
        detectionAudioReviewState.finished = false;
        animateDetectionAudioReview();
    });
    audio.addEventListener("pause", updateDetectionAudioReviewPlayback);
    audio.addEventListener("error", () => {
        const clock = document.getElementById("audio-review-clock");
        if (clock) clock.textContent = "Audio no disponible";
    });
    audio.load();
}

function updateDetectionAudioReviewPlayback() {
    const state = detectionAudioReviewState;
    if (!state) return;

    const { audio, start, end } = state;
    const duration = Math.max(0.001, end - start);
    let current = Number.isFinite(audio.currentTime) ? audio.currentTime : start;

    if (!audio.paused && current >= end - 0.025) {
        audio.pause();
        audio.currentTime = Math.min(end, audio.duration || end);
        current = end;
        state.finished = true;
    }

    const elapsed = Math.min(duration, Math.max(0, current - start));
    const progress = Math.min(100, Math.max(0, (elapsed / duration) * 100));
    const playhead = document.getElementById("audio-review-playhead");
    const clock = document.getElementById("audio-review-clock");
    const plot = document.getElementById("audio-review-plot");
    const playButton = document.getElementById("audio-review-play");

    if (playhead) playhead.style.left = `${progress}%`;
    if (clock) clock.textContent = `${formatAudioReviewTime(elapsed)} / ${formatAudioReviewTime(duration)}`;
    if (plot) plot.setAttribute("aria-valuenow", elapsed.toFixed(2));
    if (playButton) {
        const icon = playButton.querySelector("i");
        const label = state.finished ? "Repetir" : (audio.paused ? "Reproducir" : "Pausar");
        if (icon) icon.className = state.finished
            ? "bi bi-arrow-counterclockwise"
            : (audio.paused ? "bi bi-play-fill" : "bi bi-pause-fill");
        playButton.title = label;
        playButton.setAttribute("aria-label", label);
    }
}

function animateDetectionAudioReview() {
    const state = detectionAudioReviewState;
    if (!state || state.audio.paused) return;
    updateDetectionAudioReviewPlayback();
    state.frame = requestAnimationFrame(animateDetectionAudioReview);
}

async function toggleDetectionAudioReview() {
    const state = detectionAudioReviewState;
    if (!state) return;

    if (!state.audio.paused) {
        state.audio.pause();
        return;
    }

    if (state.finished || state.audio.currentTime < state.start || state.audio.currentTime >= state.end) {
        state.audio.currentTime = state.start;
        state.finished = false;
    }

    try {
        await state.audio.play();
    } catch (error) {
        console.error("No se pudo reproducir la evidencia", error);
    }
}

function resetDetectionAudioReview() {
    const state = detectionAudioReviewState;
    if (!state) return;
    state.audio.pause();
    state.audio.currentTime = state.start;
    state.finished = false;
    updateDetectionAudioReviewPlayback();
}

function seekDetectionAudioReview(event) {
    const state = detectionAudioReviewState;
    const plot = document.getElementById("audio-review-plot");
    if (!state || !plot) return;

    const bounds = plot.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - bounds.left) / bounds.width));
    state.audio.currentTime = state.start + (state.end - state.start) * ratio;
    state.finished = ratio >= 0.999;
    updateDetectionAudioReviewPlayback();
}

function handleDetectionAudioReviewKey(event) {
    const state = detectionAudioReviewState;
    if (!state) return;

    if (event.key === " " || event.key === "Enter") {
        event.preventDefault();
        toggleDetectionAudioReview();
        return;
    }

    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" ? 1 : -1;
    state.audio.currentTime = Math.min(
        state.end,
        Math.max(state.start, state.audio.currentTime + direction),
    );
    state.finished = state.audio.currentTime >= state.end;
    updateDetectionAudioReviewPlayback();
}

function setDetectionAudioVolume(value) {
    const state = detectionAudioReviewState;
    if (!state) return;
    state.audio.volume = Number(value);
    state.audio.muted = Number(value) === 0;
    updateDetectionAudioMuteIcon();
}

function toggleDetectionAudioMute() {
    const state = detectionAudioReviewState;
    if (!state) return;
    state.audio.muted = !state.audio.muted;
    updateDetectionAudioMuteIcon();
}

function updateDetectionAudioMuteIcon() {
    const state = detectionAudioReviewState;
    const button = document.getElementById("audio-review-mute");
    if (!state || !button) return;
    const muted = state.audio.muted || state.audio.volume === 0;
    const icon = button.querySelector("i");
    if (icon) icon.className = muted ? "bi bi-volume-mute-fill" : "bi bi-volume-up-fill";
    button.title = muted ? "Activar sonido" : "Silenciar";
    button.setAttribute("aria-label", button.title);
}

function markDetectionSpectrogramReady() {
    document.getElementById("audio-review-plot")?.classList.add("is-ready");
}

function markDetectionSpectrogramError() {
    const plot = document.getElementById("audio-review-plot");
    if (!plot) return;
    plot.classList.add("has-image-error");
    const loading = plot.querySelector(".audio-review-image-loading");
    if (loading) loading.textContent = "No se pudo generar el espectrograma";
}

function closeDetectionAudioReview() {
    if (detectionAudioReviewState) {
        if (detectionAudioReviewState.frame) {
            cancelAnimationFrame(detectionAudioReviewState.frame);
        }
        detectionAudioReviewState.audio.pause();
        detectionAudioReviewState.audio.removeAttribute("src");
        detectionAudioReviewState.audio.load();
    }
    detectionAudioReviewState = null;
    document.getElementById("audio-review-dialog")?.remove();
}

async function applyLearnedSuggestion(detectionId) {
    const detection = detectionCache.get(detectionId);
    const suggestion = detection ? getLearningSuggestion(detection) : null;

    if (!suggestion) {
        alert("No hay sugerencia aprendida disponible para esta deteccion.");
        return;
    }

    const correctedSpecies = suggestion.corrected_species || suggestion.effective_species || null;

    if (suggestion.status === "corrected" && !correctedSpecies) {
        alert("La sugerencia no indica una especie corregida.");
        return;
    }

    try {
        await patchDetectionReview(detectionId, {
            status: suggestion.status,
            corrected_species: suggestion.status === "corrected" ? correctedSpecies : null,
            note: `Sugerencia aprendida aplicada desde dashboard. Soporte: ${suggestion.support_count} revisiones.`,
            reviewer: "dashboard"
        });

        closeDetectionAudioReview();
        await refreshCurrentDetectionView();
    } catch (e) {
        alert(`No se pudo aplicar la sugerencia: ${e.message}`);
    }
}

async function patchDetectionReview(detectionId, payload) {
    const response = await fetch(`${DETECTION_REVIEW_BASE_URL}/${detectionId}/review`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
            "X-BirdMonitor-CSRF": "1"
        },
        body: JSON.stringify(payload)
    });

    if (!response.ok) {
        const detail = await response.text();
        throw new Error(`HTTP ${response.status}: ${detail}`);
    }

    return await response.json();
}

async function quickReviewDetection(detectionId, status) {
    const labels = {
        validated: "Detección validada desde dashboard",
        noise: "Marcada como ruido desde dashboard",
        doubtful: "Marcada como dudosa desde dashboard",
        discarded: "Descartada desde dashboard"
    };

    try {
        await patchDetectionReview(detectionId, {
            status,
            corrected_species: null,
            note: labels[status] || "Revisión desde dashboard",
            reviewer: "dashboard"
        });

        closeDetectionAudioReview();
        await refreshCurrentDetectionView();

    } catch (e) {
        alert(`No se pudo guardar la revisión: ${e.message}`);
    }
}

async function correctDetectionSpecies(detectionId) {
    const detection = detectionCache.get(detectionId);
    let speciesOptions = [];

    closeDetectionAudioReview();

    try {
        const response = await fetch(locationAwareUrl(SPECIES_OPTIONS_URL));
        speciesOptions = response.ok ? await response.json() : [];
    } catch (e) {
        console.warn("No se pudieron cargar opciones de especies", e);
    }

    openCorrectionDialog(detectionId, detection, speciesOptions);
}

function openCorrectionDialog(detectionId, detection, speciesOptions = []) {
    closeCorrectionDialog();

    const suggestion = detection ? getLearningSuggestion(detection) : null;
    const suggestionLabel = getLearningSuggestionLabel(suggestion);
    const originalSpecies = detection?.species || "Deteccion seleccionada";
    const safeOptions = [...new Set(speciesOptions)]
        .filter(value => value && value !== originalSpecies)
        .slice(0, 80);

    const dialog = document.createElement("div");
    dialog.id = "correction-dialog";
    dialog.className = "correction-dialog-backdrop";
    dialog.innerHTML = `
        <div class="correction-dialog" role="dialog" aria-modal="true" aria-labelledby="correction-dialog-title">
            <div class="correction-dialog-header">
                <div>
                    <p class="correction-dialog-eyebrow">Revision humana</p>
                    <h3 id="correction-dialog-title">Corregir especie</h3>
                </div>
                <button type="button" class="correction-dialog-close" onclick="closeCorrectionDialog()" aria-label="Cerrar">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>

            <div class="correction-dialog-body">
                <div class="correction-original">
                    <span>BirdNET propuso</span>
                    <strong>${escapeHtml(cleanName(originalSpecies))}</strong>
                </div>

                ${suggestion ? `
                    <div class="learning-suggestion-panel correction-suggestion-panel">
                        <div>
                            <span class="learning-suggestion-title">
                                <i class="bi bi-stars me-1"></i>Sugerencia aprendida
                            </span>
                            <p class="mb-0 small">
                                Propuesta: <strong>${escapeHtml(suggestionLabel)}</strong> con ${suggestion.support_count} revisiones previas.
                            </p>
                        </div>
                        <button class="btn btn-sm btn-success" onclick="applyLearnedSuggestion(${detectionId}); closeCorrectionDialog();">
                            Aplicar
                        </button>
                    </div>
                ` : `
                    <div class="correction-empty-suggestion">
                        No hay sugerencia aprendida para esta deteccion. Puedes corregirla manualmente.
                    </div>
                `}

                <label class="correction-field">
                    <span>Especie correcta</span>
                    <input
                        id="correction-species-input"
                        type="text"
                        list="correction-species-options"
                        placeholder="Ejemplo: Common Kingfisher o Ruido ambiente"
                        autocomplete="off"
                    >
                </label>

                <datalist id="correction-species-options">
                    ${safeOptions.map(option => `<option value="${escapeHtml(option)}"></option>`).join("")}
                </datalist>

                <label class="correction-field">
                    <span>Nota opcional</span>
                    <textarea
                        id="correction-note-input"
                        rows="3"
                        placeholder="Ejemplo: falso positivo por ruido de agua, solape o canto lejano"
                    ></textarea>
                </label>

                <p class="correction-helper">
                    Esta correccion se guarda como revision humana y alimenta el aprendizaje local del sistema.
                </p>
            </div>

            <div class="correction-dialog-actions">
                <button type="button" class="btn btn-outline-secondary" onclick="closeCorrectionDialog()">Cancelar</button>
                <button type="button" class="btn btn-success" onclick="submitCorrectionDialog(${detectionId})">
                    Guardar correccion
                </button>
            </div>
        </div>
    `;

    dialog.addEventListener("click", event => {
        if (event.target === dialog) closeCorrectionDialog();
    });

    document.body.appendChild(dialog);
    document.getElementById("correction-species-input")?.focus();
}

function closeCorrectionDialog() {
    document.getElementById("correction-dialog")?.remove();
}

async function submitCorrectionDialog(detectionId) {
    const speciesInput = document.getElementById("correction-species-input");
    const noteInput = document.getElementById("correction-note-input");
    const correctedSpecies = speciesInput?.value?.trim() || "";

    if (!correctedSpecies) {
        speciesInput?.focus();
        speciesInput?.classList.add("is-invalid");
        return;
    }

    try {
        await patchDetectionReview(detectionId, {
            status: "corrected",
            corrected_species: correctedSpecies,
            note: noteInput?.value?.trim() || "",
            reviewer: "dashboard"
        });

        closeCorrectionDialog();
        await refreshCurrentDetectionView();

    } catch (e) {
        alert(`No se pudo corregir la deteccion: ${e.message}`);
    }
}

async function refreshCurrentDetectionView() {
    if (currentView === "history") {
        const container = document.getElementById("main-content");
        if (container) {
            await renderHistoryView(container);
        }
        return;
    }

    if (currentView === "dashboard") {
        await updateDashboard();
    }
}

// HISTÓRICO
async function renderHistoryView(container) {
    const requestedScope = locationScopeKey();
    container.innerHTML = `<div class="d-flex justify-content-center align-items-center py-5"><div class="spinner-border text-success" role="status"></div><span class="ms-3 text-muted">Cargando base de datos completa...</span></div>`;
    try {
        const response = await fetch(locationAwareUrl(API_URL, { limit: 500 }), {
            cache: 'no-store'
        });
        const data = await response.json();
        if (requestedScope !== locationScopeKey()) return;
        const sortedData = data.reverse();
        cacheDetections(sortedData);
        let rowsHtml = '';
        sortedData.forEach(d => {
            const timeDate = new Date(d.timestamp);
            const dateStr = timeDate.toLocaleDateString();
            const timeStr = timeDate.toLocaleTimeString();
            const displayedSpecies = getDisplaySpecies(d);
            const clean = cleanName(displayedSpecies);
            const originalClean = cleanName(d.species);
            let icon = '<i class="bi bi-music-note-beamed text-success"></i>';
            if (d.species.includes("Human") || d.species.includes("Motor") || d.species.includes("Noise"))
                icon = '<i class="bi bi-boombox text-warning"></i>';
                rowsHtml += `
                <tr>
                    <td class="text-white-50 small">${d.id}</td>
                    <td>
                        ${dateStr}
                        <small class="text-muted">${timeStr}</small>
                    </td>
                    <td>
                        <div class="d-flex align-items-center">
                            <div class="me-2">${icon}</div>
                            <div>
                                ${renderSpeciesPreviewTrigger(displayedSpecies, clean)}
                                ${d.review?.status === "corrected" ? `<div class="text-muted small">Original BirdNET: ${originalClean}</div>` : ""}
                                ${buildLearningSuggestionBadge(d)}
                            </div>
                        </div>
                    </td>
                    <td>${d.device_name || 'RaspberryPi'}</td>
                    <td>
                        <div class="progress" style="height:6px;width:100px;">
                            <div class="progress-bar bg-${d.confidence > 0.8 ? 'success' : 'warning'}"
                                role="progressbar"
                                style="width:${d.confidence * 100}%">
                            </div>
                        </div>
                        <small class="text-muted">${(d.confidence * 100).toFixed(1)}%</small>
                    </td>
                    <td>${buildReviewBadge(d)}</td>
                    <td>${buildReviewActions(d)}</td>
                    <td>${buildAudioEvidenceButton(d)}</td>
                </tr>`;
        });
        container.innerHTML = `
            <div class="row mb-4 animate-fade-in">
                <div class="col-12 d-flex justify-content-between align-items-center flex-wrap gap-3">
                    <div>
                        <h3 class="fw-bold text-white"><i class="bi bi-database-fill me-2 text-accent"></i>Histórico</h3>
                        <p class="text-muted mb-0">${escapeHtml(locationLabel())} · Total registros: ${sortedData.length}</p>
                    </div>
                    <div class="d-flex flex-wrap gap-2">
                        <button class="btn btn-outline-success" onclick="downloadCSV()">
                            <i class="bi bi-filetype-csv me-2"></i>Exportar CSV
                        </button>
                        <button class="btn btn-success" onclick="downloadExcelReport(this)">
                            <i class="bi bi-file-earmark-spreadsheet me-2"></i>Exportar informe Excel
                        </button>
                    </div>
                </div>
            </div>
            <div class="card bg-dark shadow-sm border-0 flex-grow-1 d-flex flex-column animate-fade-in history-card-container">
                <div class="card-body p-0 d-flex flex-column">
                    <div class="table-container">
                        <table class="table table-dark table-hover mb-0">
                            <thead class="table-sticky-header">
                                <tr>
                                    <th class="py-3 ps-3">ID</th>
                                    <th class="py-3">Fecha</th>
                                    <th class="py-3">Especie</th>
                                    <th class="py-3">Nodo</th>
                                    <th class="py-3">Confianza</th>
                                    <th class="py-3">Revisión</th>
                                    <th class="py-3">Acciones</th>
                                    <th class="py-3 pe-3">Evidencia</th>
                                </tr>
                            </thead>
                            <tbody>${rowsHtml || `
                                <tr>
                                    <td colspan="8" class="text-center py-5 text-muted">
                                        No hay detecciones registradas para ${escapeHtml(locationLabel())} en el alcance seleccionado.
                                    </td>
                                </tr>`}</tbody>
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
    const requestedScope = locationScopeKey();
    try {
        const response = await fetch(
            locationAwareUrl(API_URL, { t: Date.now() }),
            { cache: 'no-store' }
        );
        let data = await response.json();
        if (requestedScope !== locationScopeKey() || currentView !== 'dashboard') return;
        if (!data || data.length === 0) {
            renderEmptyDashboardState();
            return;
        }
        cacheDetections(data);

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

        const birdsOnly = sortedData.filter(d => {
            const displayed = getDisplaySpecies(d).toLowerCase();
            return !displayed.includes("noise") &&
                !displayed.includes("ruido") &&
                !displayed.includes("ambiente");
        });
        safeSetText('total-counter', birdsOnly.length);

        if (birdsOnly.length > 0) {
            const latestBird = birdsOnly[0];
            safeSetText('last-activity', new Date(latestBird.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
            const counts = {};
            birdsOnly.forEach(d => {
                const species = getDisplaySpecies(d);
                counts[species] = (counts[species] || 0) + 1;
            });
            const topSpecies = Object.keys(counts).reduce((a, b) => counts[a] > counts[b] ? a : b);
            safeSetText('top-species', cleanName(topSpecies));
            await renderLiveFeedSplit(latestBird);
            renderTable(birdsOnly.slice(0, 10));
            updateChart(counts);
        } else {
            renderEmptyDashboardState();
        }
    } catch (error) { console.error("Error Dashboard:", error); }
}

function renderEmptyDashboardState() {
    safeSetText('total-counter', '0');
    safeSetText('top-species', '—');
    safeSetText('last-activity', 'Sin actividad');
    safeSetText('noise-metric', 'Sin detecciones');

    const noiseCard = document.getElementById('noise-card');
    const noiseIconBox = document.getElementById('noise-icon-box');
    const noiseIcon = document.getElementById('noise-icon');
    if (noiseCard) noiseCard.className = 'kpi-item kpi-item-secondary';
    if (noiseIconBox) noiseIconBox.className = 'icon-box bg-secondary-subtle';
    if (noiseIcon) noiseIcon.className = 'bi bi-boombox fs-3';

    const feed = document.getElementById('live-feed-container');
    if (feed) {
        feed.innerHTML = `
            <div class="empty-detection-state">
                <div class="empty-detection-icon"><i class="bi bi-geo-alt"></i></div>
                <p class="mb-1 fw-semibold">Aún no hay detecciones en ${escapeHtml(locationLabel())}</p>
                <span>Las nuevas detecciones de esta ubicación aparecerán aquí sin mezclar datos de otros lugares.</span>
            </div>`;
    }

    const tableBody = document.getElementById('history-table-body');
    if (tableBody) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center py-5 text-muted">
                    Sin registros para la ubicación y campaña seleccionadas.
                </td>
            </tr>`;
    }
    updateChart({});
}

function getDashboardHTML() {
    return `
    <section class="card kpi-panel mb-4 animate-fade-in">
        <div class="kpi-grid">
            <div class="kpi-item kpi-item-success">
                <div class="kpi-content">
                    <div>
                        <p class="text-muted small text-uppercase mb-1 fw-bold">Detecciones del sitio</p>
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
                        <span>El nodo mostrará aquí la última fuente acústica identificada en ${escapeHtml(locationLabel())}.</span>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-lg-5">
            <div class="card h-100 shadow-sm border-0 chart-card">
                <div class="card-header bg-transparent border-0 py-3">
                    <h5 class="fw-bold m-0"><i class="bi bi-pie-chart-fill me-2 text-accent"></i>Distribución de Especies</h5>
                </div>
                <div class="card-body species-chart-body">
                    <div class="species-chart-canvas-wrap">
                        <canvas id="speciesChart" aria-label="Distribución de detecciones por especie"></canvas>
                    </div>
                    <div class="species-chart-actions">
                        <button
                            id="species-chart-toggle"
                            type="button"
                            class="species-chart-toggle"
                            onclick="toggleSpeciesChartDetails()"
                            aria-controls="species-chart-all-panel"
                            aria-expanded="false"
                            hidden
                        >
                            <span>Mostrar más</span>
                            <i class="bi bi-chevron-down" aria-hidden="true"></i>
                        </button>
                    </div>
                    <div
                        id="species-chart-all-panel"
                        class="species-chart-all-panel"
                        aria-live="polite"
                        hidden
                    >
                    </div>
                </div>
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
                            <tr>
                                <th class="ps-4">Hora</th>
                                <th>Especie</th>
                                <th>Confianza</th>
                                <th>Revisión</th>
                                <th>Acciones</th>
                                <th>Audio</th>
                                <th class="text-end pe-4">ID</th>
                            </tr>
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
        const response = await fetch(locationAwareUrl(API_URL, { limit: 1000 }), {
            cache: 'no-store'
        });
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
                row.site_name || locationLabel(),
                row.site_code || getSelectedSite()?.code || '',
                row.deployment_public_id || '',
                row.filename
            ];
        });

        downloadTableCSV(
            `birdmonitor_detecciones_${locationFileToken()}_${new Date().toISOString().slice(0, 10)}.csv`,
            ['ID', 'Fecha', 'Hora', 'Timestamp_ISO', 'Especie', 'Confianza', 'Amplitud_RMS', 'Nodo_o_Device_ID', 'Ubicacion', 'Codigo_Sitio', 'ID_Campana', 'Archivo_WAV'],
            rows
        );
    } catch (e) { alert("Error exportando"); }
}

async function downloadExcelReport(button) {
    const originalContent = button?.innerHTML;

    if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Generando informe...';
    }

    try {
        const response = await fetch(locationAwareUrl('/exports/report.xlsx'), {
            cache: 'no-store'
        });
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try {
                const errorData = await response.json();
                detail = errorData.detail || detail;
            } catch (_) {
                // La respuesta puede no ser JSON si el servidor se interrumpe.
            }
            throw new Error(detail);
        }

        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
        const filename = filenameMatch?.[1]
            || `birdmonitor_informe_${locationFileToken()}_${new Date().toISOString().slice(0, 10)}.xlsx`;
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');

        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    } catch (error) {
        console.error("Error generando el informe Excel:", error);
        alert(`No se pudo generar el informe Excel: ${error.message}`);
    } finally {
        if (button) {
            button.disabled = false;
            button.innerHTML = originalContent;
        }
    }
}

function getSpeciesWikiTitle(speciesRawName) {
    let clean = speciesRawName;
    if (speciesRawName.includes('_')) clean = speciesRawName.split('_')[1];
    clean = clean.replace(/_/g, ' ').trim();
    const exactPages = { 'Merlin': 'Merlin (bird)', 'Kite': 'Kite (bird)' };
    return exactPages[clean] || clean;
}

async function getSpeciesImageUrl(speciesRawName) {
    const clean = getSpeciesWikiTitle(speciesRawName);
    if (NOISE_MAP[clean] || clean.includes("Human") || clean.includes("Motor") || clean.includes("Noise")) {
        if (clean.includes("Human")) return ASSETS_PATH + 'human.png';
        if (clean.includes("Motor") || clean.includes("Ruido") || clean.includes("Noise")) return ASSETS_PATH + 'ruido_amb.png';
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

async function getSpeciesPreviewData(speciesRawName) {
    const searchTitle = getSpeciesWikiTitle(speciesRawName);
    const fallback = {
        title: cleanName(speciesRawName),
        extract: "Sin resumen disponible.",
        imageUrl: PLACEHOLDER_IMG,
    };

    try {
        const wikiUrl = `https://en.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(searchTitle)}&prop=pageimages%7Cextracts&format=json&formatversion=2&pithumbsize=240&redirects=1&origin=*&exintro=1&explaintext=1&exsentences=2`;
        const response = await fetch(wikiUrl);
        if (!response.ok) return fallback;

        const data = await response.json();
        const page = data?.query?.pages?.[0];
        if (!page || page.missing) return fallback;

        return {
            title: page.title || fallback.title,
            extract: page.extract || fallback.extract,
            imageUrl: page.thumbnail?.source || fallback.imageUrl,
        };
    } catch (error) {
        console.error("Error cargando la vista previa de Wikipedia", error);
        return fallback;
    }
}

function ensureSpeciesPreviewCard() {
    let card = document.getElementById('species-preview-card');

    if (!card) {
        card = document.createElement('aside');
        card.id = 'species-preview-card';
        card.className = 'species-preview-card';
        card.setAttribute('role', 'tooltip');
        card.setAttribute('aria-live', 'polite');
        card.hidden = true;
        document.body.appendChild(card);
    }

    return card;
}

function positionSpeciesPreview(trigger, card) {
    const margin = 12;
    const gap = 8;
    const triggerRect = trigger.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    const maxLeft = Math.max(margin, window.innerWidth - cardRect.width - margin);
    const left = Math.min(Math.max(triggerRect.left, margin), maxLeft);
    const fitsBelow = triggerRect.bottom + gap + cardRect.height <= window.innerHeight - margin;
    const preferredTop = fitsBelow
        ? triggerRect.bottom + gap
        : triggerRect.top - cardRect.height - gap;

    card.style.left = `${left}px`;
    card.style.top = `${Math.max(margin, preferredTop)}px`;
}

async function loadSpeciesPreview(trigger, card) {
    const speciesRawName = trigger?.dataset?.species;

    if (!speciesRawName) return;

    if (!speciesPreviewCache.has(speciesRawName)) {
        speciesPreviewCache.set(speciesRawName, getSpeciesPreviewData(speciesRawName));
    }

    const preview = await speciesPreviewCache.get(speciesRawName);
    if (activeSpeciesPreviewTrigger !== trigger) return;

    const safeTitle = escapeHtml(preview.title);
    const safeExtract = escapeHtml(preview.extract);
    const safeImageUrl = escapeHtml(preview.imageUrl);

    card.innerHTML = `
        <span class="species-preview-copy">
            <span class="species-preview-source">Wikipedia</span>
            <strong class="species-preview-title">${safeTitle}</strong>
            <span class="species-preview-extract">${safeExtract}</span>
        </span>
        <img src="${safeImageUrl}" alt="${safeTitle}" onerror="this.onerror=null;this.src='${PLACEHOLDER_IMG}'">
    `;
    positionSpeciesPreview(trigger, card);
}

function showSpeciesPreview(trigger) {
    clearTimeout(speciesPreviewHideTimer);

    if (activeSpeciesPreviewTrigger && activeSpeciesPreviewTrigger !== trigger) {
        activeSpeciesPreviewTrigger.dataset.pinned = "false";
        activeSpeciesPreviewTrigger.setAttribute('aria-expanded', 'false');
    }

    activeSpeciesPreviewTrigger = trigger;
    trigger.setAttribute('aria-expanded', 'true');

    const card = ensureSpeciesPreviewCard();
    card.innerHTML = '<span class="species-preview-loading">Cargando vista previa...</span>';
    card.hidden = false;
    card.classList.add('is-preview-open');
    positionSpeciesPreview(trigger, card);
    loadSpeciesPreview(trigger, card);
}

function hideSpeciesPreview(trigger) {
    if (trigger.dataset.pinned === "true") return;

    clearTimeout(speciesPreviewHideTimer);
    speciesPreviewHideTimer = setTimeout(() => {
        if (activeSpeciesPreviewTrigger === trigger && trigger.dataset.pinned !== "true") {
            closeSpeciesPreview();
        }
    }, 80);
}

function toggleSpeciesPreview(event, trigger) {
    event.preventDefault();
    event.stopPropagation();

    if (activeSpeciesPreviewTrigger === trigger && trigger.dataset.pinned === "true") {
        closeSpeciesPreview();
        return;
    }

    trigger.dataset.pinned = "true";
    showSpeciesPreview(trigger);
}

function closeSpeciesPreview() {
    clearTimeout(speciesPreviewHideTimer);

    if (activeSpeciesPreviewTrigger) {
        activeSpeciesPreviewTrigger.dataset.pinned = "false";
        activeSpeciesPreviewTrigger.setAttribute('aria-expanded', 'false');
    }

    const card = document.getElementById('species-preview-card');
    if (card) {
        card.classList.remove('is-preview-open');
        card.hidden = true;
    }

    activeSpeciesPreviewTrigger = null;
}

document.addEventListener('click', closeSpeciesPreview);
document.addEventListener('keydown', event => {
    if (event.key === "Escape") {
        closeSpeciesPreview();
        closeDetectionAudioReview();
    }
});
window.addEventListener('resize', () => {
    const card = document.getElementById('species-preview-card');
    if (activeSpeciesPreviewTrigger && card && !card.hidden) {
        positionSpeciesPreview(activeSpeciesPreviewTrigger, card);
    }
});

async function renderLiveFeedSplit(d) {
    const container = document.getElementById('live-feed-container');
    if (!container) return;
    const displayedSpecies = getDisplaySpecies(d);
    const species = cleanName(displayedSpecies);
    const percent = (d.confidence * 100).toFixed(0);
    const spectrogramUrl = `${IMG_BASE_URL}${d.filename.replace(/\.wav/g, '')}.png`;
    const timeStr = new Date(d.timestamp).toLocaleTimeString();
    const speciesPhotoUrl = await getSpeciesImageUrl(displayedSpecies);

    container.innerHTML = `
        <div class="main-detection-split enhanced-detection w-100">
            <div class="split-photo">
                <img src="${speciesPhotoUrl}" class="bird-photo" alt="Imagen de referencia de ${escapeHtml(species)}" onerror="this.src='${PLACEHOLDER_IMG}'">
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
                ${buildLearningSuggestionPanel(d)}
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
        const displayedSpecies = getDisplaySpecies(d);
        const clean = cleanName(displayedSpecies);
        const originalClean = cleanName(d.species);

        let icon = '<i class="bi bi-feather text-success me-2"></i>';

        if (NOISE_MAP[clean] || d.species.includes("Human") || d.species.includes("Motor")) {
            icon = '<i class="bi bi-boombox text-muted me-2"></i>';
        }

        tbody.innerHTML += `
            <tr>
                <td class="ps-4 fw-bold text-muted">
                    ${new Date(d.timestamp).toLocaleTimeString()}
                </td>

                <td>
                    <div class="d-flex align-items-center">
                        ${icon}
                        <div>
                            ${renderSpeciesPreviewTrigger(displayedSpecies, clean)}
                            ${d.review?.status === "corrected" ? `<div class="text-muted small">Original: ${originalClean}</div>` : ""}
                            ${buildLearningSuggestionBadge(d)}
                        </div>
                    </div>
                </td>

                <td>
                    <span class="badge bg-dark-subtle text-success border">
                        ${(d.confidence * 100).toFixed(0)}%
                    </span>
                </td>

                <td>
                    ${buildReviewBadge(d)}
                </td>

                <td>
                    ${buildReviewActions(d)}
                </td>

                <td>${buildAudioEvidenceButton(d, imgUrl)}</td>

                <td class="text-end pe-4 text-muted small">
                    #${d.id}
                </td>
            </tr>
        `;
    });
}

function updateChart(counts) {
    const canvas = document.getElementById('speciesChart');
    if (!canvas) return;

    latestSpeciesCounts = { ...counts };
    if (myChart) { myChart.destroy(); }

    const ctx = canvas.getContext('2d');
    const allEntries = Object.entries(counts)
        .sort((a, b) => b[1] - a[1] || cleanName(a[0]).localeCompare(cleanName(b[0]), 'es'));
    const hasMoreSpecies = allEntries.length > SPECIES_CHART_INITIAL_LIMIT;
    if (!hasMoreSpecies) speciesChartExpanded = false;
    const allDetectionsTotal = allEntries.reduce(
        (sum, [, count]) => sum + count,
        0
    );
    const labels = allEntries.map(([species]) => cleanName(species));
    const values = allEntries.map(([, count]) => count);
    const colors = allEntries.map(([species]) => getSpeciesChartColor(species));

    myChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: colors, borderWidth: 0 }] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            plugins: {
                legend: {
                    display: true,
                    position: window.innerWidth <= 576 ? 'bottom' : 'right',
                    labels: {
                        color: '#5f6f65',
                        boxWidth: 32,
                        boxHeight: 12,
                        padding: 14,
                        filter(legendItem) {
                            return legendItem.index < SPECIES_CHART_INITIAL_LIMIT;
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label(context) {
                            const percentage = allDetectionsTotal > 0
                                ? ((context.parsed / allDetectionsTotal) * 100).toFixed(1)
                                : '0.0';
                            return `${context.label}: ${context.parsed} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });

    renderAllSpeciesPanel(allEntries, hasMoreSpecies);
}

function renderAllSpeciesPanel(allEntries, hasMoreSpecies) {
    const panel = document.getElementById('species-chart-all-panel');
    const toggle = document.getElementById('species-chart-toggle');
    if (!panel || !toggle) return;

    const previousScrollTop = panel.scrollTop;
    const totalDetections = allEntries.reduce((sum, [, count]) => sum + count, 0);
    panel.hidden = !hasMoreSpecies || !speciesChartExpanded;
    panel.innerHTML = `
        <div class="species-chart-all-heading">
            <strong>Todas las especies</strong>
            <span>${allEntries.length} registradas</span>
        </div>
        <div class="species-chart-all-grid">
            ${allEntries.map(([species, count]) => {
        const cleanSpecies = cleanName(species);
        const percentage = totalDetections > 0
            ? ((count / totalDetections) * 100).toFixed(1)
            : '0.0';

        return `
            <div class="species-chart-all-item" title="${escapeHtml(cleanSpecies)}">
                <span
                    class="species-chart-all-swatch"
                    style="--species-color:${getSpeciesChartColor(species)}"
                    aria-hidden="true"
                ></span>
                <span class="species-chart-all-name">${escapeHtml(cleanSpecies)}</span>
                <span class="species-chart-all-value">
                    <strong>${count}</strong> · ${percentage}%
                </span>
            </div>
        `;
            }).join('')}
        </div>
    `;
    if (speciesChartExpanded) panel.scrollTop = previousScrollTop;

    toggle.hidden = !hasMoreSpecies;
    toggle.setAttribute('aria-expanded', String(speciesChartExpanded));
    toggle.innerHTML = speciesChartExpanded
        ? '<span>Mostrar menos</span><i class="bi bi-chevron-up" aria-hidden="true"></i>'
        : `<span>Mostrar más (${allEntries.length - SPECIES_CHART_INITIAL_LIMIT})</span><i class="bi bi-chevron-down" aria-hidden="true"></i>`;
}

function toggleSpeciesChartDetails() {
    speciesChartExpanded = !speciesChartExpanded;
    updateChart(latestSpeciesCounts);
}

function getSpeciesChartColor(species) {
    const key = String(species || 'Desconocido');
    if (speciesChartColorMap.has(key)) return speciesChartColorMap.get(key);

    const index = speciesChartColorMap.size;
    const hue = (142 + index * 137.508) % 360;
    const saturation = 52 + (index % 3) * 6;
    const lightness = 40 + (Math.floor(index / 3) % 2) * 8;
    const color = `hsl(${hue.toFixed(1)}, ${saturation}%, ${lightness}%)`;

    speciesChartColorMap.set(key, color);
    return color;
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

    const missing = value === null || value === undefined || value === '';
    const numericValue = missing ? Number.NaN : Number(value);
    const available = !missing && Number.isFinite(numericValue);
    const clampedVal = available ? Math.min(Math.max(numericValue, min), max) : min;
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
    const displayVal = available
        ? ((numericValue % 1 === 0) ? numericValue.toFixed(0) : numericValue.toFixed(3))
        : '—';
    const textColor = !available
        ? '#879389'
        : pct >= 0.65 ? '#2f6f4e' : pct >= 0.35 ? '#a66f2f' : '#9c3f3f';
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

function selectScienceNode(deviceId) {
    const parsed = Number(deviceId);
    selectedScienceDeviceId = Number.isInteger(parsed) ? parsed : null;
    const container = document.getElementById('main-content');
    if (container && currentView === 'science') renderScienceView(container);
}

// VISTA ANÁLISIS ECO
async function renderScienceView(container) {
    const requestedScope = locationScopeKey();
    container.innerHTML = `
        <div class="d-flex justify-content-center align-items-center py-5">
            <div class="spinner-grow text-info" role="status"></div>
            <span class="ms-3 text-white">Procesando datos del nodo...</span>
        </div>`;
    try {
        const response = await fetch(locationAwareUrl("/analytics/biodiversity"), {
            cache: 'no-store'
        });
        const report = await response.json();
        if (requestedScope !== locationScopeKey() || currentView !== 'science') return;
        currentScienceReport = report || [];
        if (!report || report.length === 0) {
            container.innerHTML = `
                <div class="alert alert-warning text-center mt-4">
                    No hay una campaña o nodo asociado a ${escapeHtml(locationLabel())} en el alcance seleccionado.
                </div>`;
            return;
        }

        const requestedReport = report.find(
            item => Number(item.device_id) === selectedScienceDeviceId
        );
        const r = requestedReport || report[0];
        selectedScienceDeviceId = Number(r.device_id);
        const nodeSelectorHTML = report.length > 1
            ? `
                <label class="visually-hidden" for="science-node-select">Nodo analizado</label>
                <select id="science-node-select"
                        class="form-select form-select-sm bg-dark text-white border-secondary"
                        onchange="selectScienceNode(this.value)"
                        aria-label="Seleccionar nodo analizado">
                    ${report.map(item => `
                        <option value="${Number(item.device_id)}"
                                ${Number(item.device_id) === selectedScienceDeviceId ? 'selected' : ''}>
                            ${escapeHtml(item.node_name || `Nodo ${item.device_id}`)} · ${escapeHtml(item.zona || 'Sin ubicación')}
                        </option>
                    `).join('')}
                </select>`
            : '';
        const metricNumber = key => {
            if (r.metrics_available !== true) return null;
            const raw = r[key];
            if (raw === null || raw === undefined || raw === '') return null;
            const value = Number(raw);
            return Number.isFinite(value) ? value : null;
        };
        const metricText = (key, decimals = 3) => {
            const value = metricNumber(key);
            return value === null ? '—' : value.toFixed(decimals);
        };
        const metricsReady = r.metrics_available === true;
        const interpretacion = 'DESCRIPTIVO';
        const speciesCount = Number(r.riqueza) || 0;
        const theoreticalShannonMax = speciesCount > 1
            ? Math.log(speciesCount)
            : null;
        const shannonGaugeMax = theoreticalShannonMax || 1;
        const ndsiValue = metricNumber('ndsi_avg');
        const ndsiColor = ndsiValue === null
            ? '#879389'
            : ndsiValue >= 0 ? '#2f6f4e' : '#9c3f3f';
        const ndsiMagnitude = ndsiValue === null ? 0 : Math.abs(ndsiValue);
        const formatMetricDate = value => {
            if (!value) return '';
            const date = new Date(value);
            return Number.isNaN(date.getTime())
                ? ''
                : date.toLocaleString('es-ES', {
                    day: '2-digit',
                    month: '2-digit',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });
        };
        const metricPeriod = [
            formatMetricDate(r.metric_period_start),
            formatMetricDate(r.metric_period_end)
        ].filter(Boolean).join(' – ');
        const metricsNote = metricsReady
            ? `${r.metric_samples} muestras del nodo · ${escapeHtml(metricPeriod)} · método ${escapeHtml(r.metrics_version || 'maad-v2')}`
            : `Esperando nuevas muestras con el método corregido ${escapeHtml(r.metrics_version || 'maad-v2')}; la serie anterior no se mezcla.`;

        // ── Gauges biodiversidad — LAYOUT 3+2 
        const g1 = buildGaugeSVG(r.shannon, 0, shannonGaugeMax, '#405f82', "Shannon H'",
            `Diversidad del reparto de eventos BirdNET entre las especies detectadas. ${theoreticalShannonMax === null ? 'Con una sola especie H′ es 0.' : `Su máximo para este conjunto es ln(S) = ${theoreticalShannonMax.toFixed(3)}.`} No clasifica por sí solo la calidad del ecosistema.`);
        const g2 = buildGaugeSVG(r.simpson, 0, 1, '#326f72', "Simpson 1-D",
            "Probabilidad de que dos eventos de detección tomados al azar correspondan a especies distintas.");
        const g3 = buildGaugeSVG(r.pielou, 0, 1, '#2f6f4e', "Pielou J'",
            "Uniformidad del reparto de eventos entre las especies detectadas. Con una sola especie no está definido.");
        const g4 = buildGaugeSVG(Math.min(r.riqueza, 30), 0, 30, '#a66f2f', "Especies S",
            "Número de especies distintas registradas por BirdNET tras aplicar las revisiones humanas. No es un inventario exhaustivo.");
        const g5 = buildGaugeSVG(Math.min(r.abundancia, 999), 0, 999, '#6f7f5a', "Eventos N",
            "Número de eventos acústicos de detección. Varios cantos pueden pertenecer al mismo ejemplar, por lo que N no equivale a individuos.");

        // Fila superior: 3 gauges | Fila inferior: 2 gauges centrados
        const gaugesBioHTML = `
        <div class="gauges-grid">
            <div class="gauges-row-top">${g1}${g2}${g3}</div>
            <div class="gauges-row-bot">${g4}${g5}</div>
        </div>`;

        // ── Gauges entropía acústica — los 3 EN UNA SOLA FILA ────────────
        const ge1 = buildGaugeSVG(metricNumber('ht_avg'), 0, 1, '#326f72', "Ht",
            "Dispersión temporal de la energía. Un fondo continuo también puede producir valores altos.");
        const ge2 = buildGaugeSVG(metricNumber('hf_avg'), 0, 1, '#405f82', "Hf",
            "Dispersión de la energía entre frecuencias; describe el audio registrado, no la salud del ecosistema.");
        const ge3 = buildGaugeSVG(metricNumber('h_avg'), 0, 1, '#2f6f4e', "H",
            "Entropía acústica compuesta H = Ht × Hf. Es un descriptor del paisaje sonoro sin umbral ecológico universal.");

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
                    <i class="bi bi-geo-alt-fill me-1"></i>${escapeHtml(r.zona || 'Zona desconocida')}
                    &nbsp;·&nbsp;<i class="bi bi-activity me-1"></i>${r.abundancia} detecciones
                    &nbsp;·&nbsp;<i class="bi bi-list-stars me-1"></i>${r.riqueza} especies únicas
                </p>
            </div>
            <div class="d-flex align-items-center gap-2 align-self-center">
                ${nodeSelectorHTML}
                <button class="btn btn-success btn-sm" onclick="downloadScienceCSV()">
                    <i class="bi bi-filetype-csv me-2"></i>Exportar índices
                </button>
                <span class="badge bg-secondary px-3 py-2 fs-6"
                      title="Lectura orientativa de los registros, no una calificación del ecosistema">
                    <i class="bi bi-info-circle me-1"></i>${escapeHtml(interpretacion)}
                </span>
            </div>
        </div>

        <!-- Tarjetas compuestas: biodiversidad | paisaje sonoro -->
        <div class="row g-3 mb-3 animate-fade-in science-composite-row">

            <div class="col-xl-7 d-flex">
                <div class="card border-0 bg-dark science-composite-card">
                    <div class="card-body science-card-body">
                        <div class="science-card-head">
                            <p class="sci-section-title"><i class="bi bi-bar-chart-steps me-1"></i>Diversidad de detecciones</p>
                        </div>

                        <div class="science-panel-section">
                            ${gaugesBioHTML}
                            <p class="text-muted mb-0" style="font-size:0.7rem;margin-top:0.5rem;">
                                <i class="bi bi-info-circle me-1"></i>Pasa el cursor sobre cada medidor para ver su definición.
                            </p>
                        </div>

                        <div class="science-panel-divider"></div>

                        <div class="science-panel-section">
                            <p class="sci-section-title"><i class="bi bi-bar-chart-fill me-1"></i>Resumen de indicadores</p>
                            <div class="science-chart-frame">
                                <canvas id="scienceBarChart"></canvas>
                            </div>
                            <p class="text-muted mb-0 mt-2" style="font-size:0.68rem;">
                                <i class="bi bi-info-circle me-1"></i>No compares la altura entre barras:
                                usan escalas y periodos distintos; consulta cada valor por separado.
                            </p>
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
                                            stroke="${ndsiColor}"
                                            stroke-width="6"
                                            stroke-dasharray="${ndsiMagnitude * 75.4} 150.8"
                                            stroke-dashoffset="37.7"
                                            stroke-linecap="round"
                                            transform="rotate(-90 28 28)"/>
                                    </svg>
                                </div>
                                <div class="soundscape-copy">
                                    <div class="ndsi-badge" style="color:${ndsiColor};">
                                        ${metricText('ndsi_avg')}
                                    </div>
                                    <p>
                                        ${ndsiValue === null
                ? 'Sin muestras comparables todavía'
                : ndsiValue >= 0
                    ? 'Mayor energía relativa entre 1 y 10 kHz'
                    : 'Mayor energía relativa entre 0 y 1 kHz'}
                                        <br><span class="text-white-50">Rango: −1 (0–1 kHz) → +1 (1–10 kHz)</span>
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
                                <span class="index-bar-label" data-gauge-tip="ACI: variación temporal de amplitud por banda. Depende de duración, ruido y parámetros; no mide por sí solo biodiversidad.">ACI</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((metricNumber('aci_avg') || 0) / 2000 * 100, 100)}%;background:#405f82;"></div></div>
                                <span class="index-bar-val">${metricText('aci_avg', 1)}</span>
                            </div>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="ADI: reparto de la ocupación acústica entre bandas de 250 Hz a 10 kHz. No equivale a diversidad de especies.">ADI</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((metricNumber('adi_avg') || 0) / Math.log(10) * 100, 100)}%;background:#2f6f4e;"></div></div>
                                <span class="index-bar-val">${metricText('adi_avg')}</span>
                            </div>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="AEI: desigualdad de la ocupación entre bandas (Gini). Alto significa una ocupación más desigual, no mayor calidad.">AEI</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((metricNumber('aei_avg') || 0) * 100, 100)}%;background:#a66f2f;"></div></div>
                                <span class="index-bar-val">${metricText('aei_avg')}</span>
                            </div>
                            <div class="index-bar-row">
                                <span class="index-bar-label" data-gauge-tip="BIO: energía relativa registrada entre 2 y 10 kHz. También puede incluir ruido no biológico en esa banda.">BIO</span>
                                <div class="index-bar-track"><div class="index-bar-fill" style="width:${Math.min((metricNumber('bio_avg') || 0), 100)}%;background:#6f7f5a;"></div></div>
                                <span class="index-bar-val">${metricText('bio_avg', 2)}</span>
                            </div>
                            <p class="text-muted mt-2 mb-0" style="font-size:0.68rem;">
                                <i class="bi bi-info-circle me-1"></i>${metricsNote}
                                Las longitudes son una guía visual, no umbrales ecológicos.
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
                                <i class="bi bi-map-fill me-1"></i>Ubicación del nodo y entorno de referencia
                            </p>
                            <p class="text-muted mb-0 mt-2" style="font-size:0.72rem;">
                                El área acústica es orientativa y local; no representa una cobertura garantizada ni permite localizar cada ave.
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
                    labels: ["Shannon (H')", 'Simpson (1-D)', "Pielou (J')", 'Especies (S/30)', 'Entropía (H)'],
                    datasets: [{
                        label: 'Valor',
                        data: [
                            r.shannon,
                            r.simpson,
                            r.pielou ?? null,
                            parseFloat((r.riqueza / 30).toFixed(3)),
                            metricNumber('h_avg')
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
                                        theoreticalShannonMax === null
                                            ? 'Con una sola especie H′ es 0'
                                            : `Máximo del conjunto actual: ln(S) = ${theoreticalShannonMax.toFixed(3)}`,
                                        'Distribución de eventos; rango 0–1',
                                        'Equidad de eventos; no definida si S = 1',
                                        'Especies detectadas / 30 (solo escala visual)',
                                        'H = Ht × Hf; descriptor acústico sin umbral de salud',
                                    ];
                                    return tips[ctx.dataIndex] || '';
                                }
                            }
                        }
                    },
                    scales: {
                        y: { min: 0, max: Math.max(1, Math.ceil(shannonGaugeMax * 10) / 10), grid: { color: '#dde3d8' }, ticks: { color: '#5f6f65', font: { size: 11 } } },
                        x: { grid: { display: false }, ticks: { color: '#5f6f65', font: { size: 12 } } }
                    }
                }
            });
        }

        // Mapa Leaflet: punto real del mismo nodo que muestran los índices.
        fetch(locationAwareUrl('/analytics/map', { device_id: r.device_id }))
            .then(res => res.json())
            .then(mapData => {
                if (requestedScope !== locationScopeKey() || currentView !== 'science') return;
                const mapContainer = document.getElementById('biodiversityMap');
                if (!mapContainer) return;
                if (
                    mapData.available === false
                    || !Number.isFinite(Number(mapData.lat))
                    || !Number.isFinite(Number(mapData.lon))
                ) {
                    mapContainer.innerHTML = `
                        <div class="h-100 d-flex align-items-center justify-content-center p-4">
                            <div class="alert alert-warning mb-0 text-center">
                                <i class="bi bi-geo-alt me-2"></i>${escapeHtml(mapData.error || 'Ubicación del nodo no disponible.')}
                            </div>
                        </div>`;
                    return;
                }

                const latLng = [Number(mapData.lat), Number(mapData.lon)];
                const map = L.map('biodiversityMap').setView(latLng, 18);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; OpenStreetMap'
                }).addTo(map);

                const configuredRadius = Number(mapData.reference_radius_m);
                const radiusM = Math.max(
                    0,
                    Number.isFinite(configuredRadius) ? configuredRadius : 0
                );
                const locationSourceLabels = {
                    manual: 'coordenadas configuradas',
                    gps: 'GPS',
                    ip_geolocation: 'geolocalización IP aproximada',
                    unknown: 'procedencia sin documentar'
                };
                const locationSource = locationSourceLabels[mapData.location_source]
                    || 'procedencia sin documentar';
                const rangeLine = radiusM > 0
                    ? `Radio visual: ${radiusM.toFixed(0)} m · no calibrado`
                    : 'Radio oculto: se requieren coordenadas manuales o GPS';
                const mapEventCount = Number(mapData.event_count);
                const mapSpeciesCount = Number(mapData.species_count);
                const mapCountLines = (
                    Number.isFinite(mapEventCount)
                    && Number.isFinite(mapSpeciesCount)
                )
                    ? `Eventos registrados: <b>${mapEventCount}</b><br>
                       Especies detectadas: <b>${mapSpeciesCount}</b><br>`
                    : '';
                const marker = L.marker(latLng).addTo(map);
                marker.bindPopup(`
                    <b>${escapeHtml(mapData.node_name || 'Nodo acústico')}</b><br>
                    ${escapeHtml(mapData.ciudad || 'Sin ubicación nominal')}<br>
                    ${mapCountLines}
                    Shannon de eventos: <b>${mapData.shannon ?? '—'}</b><br>
                    <span style="font-size:0.82em;">
                        Ubicación: ${escapeHtml(locationSource)}<br>${rangeLine}
                    </span>
                `).openPopup();

                if (radiusM > 0) {
                    const circle = L.circle(latLng, {
                        color: '#536f61',
                        fillColor: '#7b9586',
                        fillOpacity: 0.08,
                        opacity: 0.9,
                        dashArray: '7 7',
                        weight: 2,
                        radius: radiusM
                    }).addTo(map);
                    circle.bindTooltip(
                        `${escapeHtml(mapData.range_label || 'Entorno local orientativo')} · ${radiusM.toFixed(0)} m`
                    );
                    map.fitBounds(circle.getBounds(), { padding: [38, 38], maxZoom: 18 });
                }
            })
            .catch(() => {
                const mapContainer = document.getElementById('biodiversityMap');
                if (mapContainer) {
                    mapContainer.innerHTML = `
                        <div class="h-100 d-flex align-items-center justify-content-center p-4">
                            <div class="alert alert-warning mb-0">No se pudo cargar el mapa del nodo.</div>
                        </div>`;
                }
            });

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
        r.device_id ?? '',
        r.node_name || '',
        r.zona || 'Zona desconocida',
        'DESCRIPTIVO',
        r.abundancia ?? 0,
        r.riqueza ?? 0,
        r.shannon ?? 0,
        r.simpson ?? 0,
        r.pielou ?? '',
        r.detection_period_start ?? '',
        r.detection_period_end ?? '',
        r.metrics_version ?? '',
        r.metric_samples ?? 0,
        r.metric_duration_seconds ?? 0,
        r.rms_avg ?? '',
        r.aci_avg ?? '',
        r.adi_avg ?? '',
        r.aei_avg ?? '',
        r.bio_avg ?? '',
        r.ndsi_avg ?? '',
        r.ht_avg ?? '',
        r.hf_avg ?? '',
        r.h_avg ?? ''
    ]);

    downloadTableCSV(
        `birdmonitor_indices_${locationFileToken()}_${new Date().toISOString().slice(0, 10)}.csv`,
        [
            'ID_Nodo',
            'Nodo',
            'Zona',
            'Alcance_Interpretacion',
            'Eventos_Deteccion_N',
            'Especies_Detectadas_S',
            'Shannon_H',
            'Simpson_1-D',
            'Pielou_J',
            'Inicio_Periodo_Detecciones',
            'Fin_Periodo_Detecciones',
            'Version_Metricas_Acusticas',
            'Muestras_Acusticas',
            'Duracion_Acustica_Segundos',
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

// NODOS Y UBICACIONES HISTÓRICAS
async function selectLocationFromNodes(siteId) {
    await changeLocationSite(siteId);
    switchView('dashboard');
}

async function renderNodesView(container) {
    container.innerHTML = `<div class="text-center py-5"><div class="spinner-border text-success"></div></div>`;
    try {
        if (!locationContextReady) await initializeLocationContext();
        const siteDeployments = await Promise.all(
            locationSites.map(async site => ({
                site,
                deployments: Number(site.id) === Number(selectedSiteId)
                    ? locationDeployments
                    : await fetchLocationDeployments(site.id)
            }))
        );

        const nodesHtml = siteDeployments.map(({ site, deployments }) => {
            const activeDeployment = deployments.find(item => item.active);
            const latestDeployment = activeDeployment || deployments[0] || null;
            const selected = Number(site.id) === Number(selectedSiteId);
            const locationParts = [site.municipality, site.region, site.country_code]
                .filter(Boolean)
                .join(', ');
            const statusLabel = activeDeployment ? 'UBICACIÓN ACTUAL' : 'HISTÓRICO';
            const statusClass = activeDeployment ? 'bg-success' : 'bg-secondary';
            const latestPeriod = latestDeployment
                ? `${formatDeploymentDate(latestDeployment.started_at)}${latestDeployment.active ? ' – actualidad' : ` – ${formatDeploymentDate(latestDeployment.ended_at)}`}`
                : 'Sin campañas';

            return `
                <div class="col-md-6 col-xl-4 mb-4">
                    <div class="card bg-dark text-white shadow-sm node-card h-100 ${selected ? 'border-success' : 'border-0'}">
                        <div class="card-body d-flex flex-column">
                            <div class="d-flex justify-content-between align-items-start gap-2 mb-3">
                                <h5 class="fw-bold m-0">
                                    <i class="bi bi-geo-alt-fill text-info me-2"></i>${escapeHtml(site.name)}
                                </h5>
                                <span class="badge ${statusClass}">${statusLabel}</span>
                            </div>
                            <p class="text-muted small mb-2">
                                <i class="bi bi-map me-1"></i>${escapeHtml(locationParts || 'Ubicación configurada')}
                            </p>
                            <p class="text-muted small mb-2">
                                <i class="bi bi-cpu me-1"></i>${escapeHtml(latestDeployment?.device_name || 'Sin nodo asociado')}
                            </p>
                            <p class="text-muted small mb-3">
                                <i class="bi bi-calendar-range me-1"></i>${escapeHtml(latestPeriod)}
                            </p>
                            <div class="row g-2 mb-3">
                                <div class="col-4"><div class="p-2 rounded bg-dark-subtle text-center"><strong>${Number(site.detection_count) || 0}</strong><br><small class="text-muted">registros</small></div></div>
                                <div class="col-4"><div class="p-2 rounded bg-dark-subtle text-center"><strong>${Number(site.audio_metric_count) || 0}</strong><br><small class="text-muted">métricas</small></div></div>
                                <div class="col-4"><div class="p-2 rounded bg-dark-subtle text-center"><strong>${deployments.length}</strong><br><small class="text-muted">campañas</small></div></div>
                            </div>
                            <button
                                type="button"
                                class="btn ${selected ? 'btn-success' : 'btn-outline-success'} mt-auto"
                                onclick="selectLocationFromNodes(${Number(site.id)})"
                            >
                                <i class="bi bi-bar-chart-line me-2"></i>${selected ? 'Viendo estos datos' : 'Ver datos'}
                            </button>
                        </div>
                    </div>
                </div>`;
        }).join('');

        container.innerHTML = `
            <div class="row mb-4 animate-fade-in">
                <div class="col-12 d-flex justify-content-between align-items-start flex-wrap gap-3">
                    <div>
                        <h3 class="fw-bold text-white"><i class="bi bi-router me-2 text-accent"></i>Nodo y ubicaciones</h3>
                        <p class="text-muted mb-0">
                            Cada tarjeta conserva el historial independiente del mismo nodo. La ubicación actual aparece marcada en verde.
                        </p>
                    </div>
                    <button type="button" class="btn btn-success" onclick="openPhysicalLocationDialog()">
                        <i class="bi bi-geo-alt-fill me-2"></i>Cambiar ubicación física
                    </button>
                </div>
            </div>
            <div class="row animate-fade-in">${nodesHtml}</div>`;
    } catch (e) {
        container.innerHTML = `<div class="alert alert-danger">Error cargando ubicaciones: ${escapeHtml(e.message)}</div>`;
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
    const requestedScope = locationScopeKey();
    try {
        const res = await fetch(locationAwareUrl('/analytics/daily-activity', {
            date: dateStr
        }));
        const data = await res.json();
        if (requestedScope !== locationScopeKey() || currentView !== 'daily') return;
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
        `birdmonitor_actividad_horaria_${locationFileToken()}_${date}.csv`,
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
document.addEventListener('DOMContentLoaded', async () => {
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

    const container = document.getElementById('main-content');
    if (container) {
        container.innerHTML = `
            <div class="d-flex justify-content-center align-items-center py-5">
                <div class="spinner-border text-success" role="status"></div>
                <span class="ms-3 text-muted">Cargando ubicación activa...</span>
            </div>`;
    }

    try {
        await initializeLocationContext();
        switchView('dashboard');
        setInterval(updateDashboard, 4000);
        setInterval(refreshLocationCatalog, 15000);
        if (new URLSearchParams(window.location.search).get('location_setup') === '1') {
            await openPhysicalLocationDialog({ startup: true });
        }
    } catch (error) {
        console.error('No se pudo inicializar el contexto de ubicación:', error);
        const siteSelect = document.getElementById('location-site-select');
        if (siteSelect) {
            siteSelect.innerHTML = '<option>Ubicación no disponible</option>';
            siteSelect.disabled = true;
        }
        if (container) {
            container.innerHTML = `
                <div class="alert alert-danger mt-4">
                    No se puede mostrar el dashboard sin una ubicación válida: ${escapeHtml(error.message)}
                </div>`;
        }
    }
});