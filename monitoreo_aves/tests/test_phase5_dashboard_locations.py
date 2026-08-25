from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_inicializa_el_sitio_activo_antes_de_cargar_datos():
    javascript = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "activeSite || locationSites[0]" in javascript
    assert "await initializeLocationContext();" in javascript
    assert "switchView('dashboard');" in javascript
    assert javascript.index("await initializeLocationContext();") < javascript.rindex(
        "switchView('dashboard');"
    )


def test_consultas_y_exportaciones_del_dashboard_llevan_contexto_geografico():
    javascript = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    expected_scoped_calls = (
        "locationAwareUrl(API_URL, { limit: 500 })",
        "locationAwareUrl(API_URL, { t: Date.now() })",
        "locationAwareUrl(API_URL, { limit: 1000 })",
        "locationAwareUrl('/exports/report.xlsx')",
        'locationAwareUrl("/analytics/biodiversity")',
        "locationAwareUrl('/analytics/map', { device_id: r.device_id })",
        "locationAwareUrl('/analytics/daily-activity'",
        "locationAwareUrl(SPECIES_OPTIONS_URL)",
    )
    for scoped_call in expected_scoped_calls:
        assert scoped_call in javascript

    assert "url.searchParams.set('site_id'" in javascript
    assert "url.searchParams.set('deployment_id'" in javascript


def test_dashboard_no_conserva_sevilla_como_ubicacion_visual_fija():
    html = (PROJECT_ROOT / "frontend" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "v2.1 · Sevilla, ES" not in html
    assert 'id="location-site-select"' in html
    assert 'id="location-deployment-select"' in html
    assert 'id="topbar-location-name"' not in html
    assert "Nodo Edge · BirdNET · Bioacústica" not in html

    javascript = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )
    assert "const shortName = site.municipality || site.name" in javascript
    assert "const allLabel = 'Historial completo'" in javascript


def test_control_fisico_esta_separado_del_selector_historico_y_usa_csrf():
    javascript = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "Cambiar ubicación física" in javascript
    assert "Consultar datos históricos no mueve el nodo" in javascript
    assert "Confirmo que la caja ya está físicamente" in javascript
    assert "X-BirdMonitor-CSRF': '1'" in javascript
    assert "setInterval(refreshLocationCatalog, 15000)" in javascript
    assert "openPhysicalLocationDialog({ startup: true })" in javascript


def test_dashboard_resuelve_espectrogramas_por_deteccion_y_no_por_ruta_plana():
    javascript = (PROJECT_ROOT / "frontend" / "js" / "dashboard.js").read_text(
        encoding="utf-8"
    )

    assert "d.spectrogram_url" in javascript
    assert "DETECTION_REVIEW_BASE_URL" in javascript
    assert 'const IMG_BASE_URL = "/spectrograms/"' not in javascript
