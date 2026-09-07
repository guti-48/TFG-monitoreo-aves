// Ejecutar: node --test tests/test_location_coordinates_ui.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function dashboard() {
    const fields = {};
    for (const [id, value] of Object.entries({lat: '37,391234', lon: '-6.012345', accuracy: ''})) {
        fields[`physical-location-${id}`] = { value };
    }
    const sandbox = {
        document: {
            getElementById: id => fields[id], addEventListener() {},
            createElement: () => ({ style: {} }), body: { appendChild() {} },
        },
        window: { location: { origin: 'http://localhost', hostname: 'localhost' }, addEventListener() {} },
        console,
    };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/js/dashboard.js'), 'utf8'), sandbox);
    return { sandbox, fields };
}

test('coordenadas decimales con coma y precisión desconocida', () => {
    const { sandbox } = dashboard();
    const point = sandbox.readPhysicalLocationCoordinates();
    assert.equal(point.lat, 37.391234);
    assert.equal(point.lon, -6.012345);
    assert.equal(point.location_accuracy_m, null);
});

test('rechaza valores vacíos, no finitos y fuera de rango', () => {
    for (const [key, value] of [['lat', ''], ['lat', '91'], ['lon', '-181'], ['lat', 'NaN'], ['accuracy', '-1']]) {
        const { sandbox, fields } = dashboard();
        fields[`physical-location-${key}`].value = value;
        assert.throws(() => sandbox.readPhysicalLocationCoordinates());
    }
});

test('permite cero como coordenada y como precisión explícita', () => {
    const { sandbox, fields } = dashboard();
    for (const field of Object.values(fields)) field.value = '0';
    const point = sandbox.readPhysicalLocationCoordinates();
    assert.equal(point.lat, 0);
    assert.equal(point.lon, 0);
    assert.equal(point.location_accuracy_m, 0);
});

test('el mapa sincroniza clic y arrastre, sin inventar precisión, y se libera al cerrar', () => {
    const { sandbox, fields } = dashboard();
    fields['physical-location-coordinates'] = { open: true };
    fields['physical-location-accuracy'].value = '150';
    const handlers = {};
    let removed = false;
    let markerPoint;
    const map = { setView() { return this; }, on(event, fn) { handlers[event] = fn; }, remove() { removed = true; } };
    const marker = {
        addTo() { return this; }, on(event, fn) { handlers[event] = fn; },
        setLatLng(point) { markerPoint = point; }, getLatLng() { return { lat: 37.4, lng: -6 }; },
    };
    sandbox.L = { map: () => map, marker: () => marker, tileLayer: () => ({ addTo() {} }) };
    sandbox.initializePhysicalLocationMap();
    handlers.click({ latlng: { lat: 37.391234, lng: -6.012345 } });
    assert.equal(fields['physical-location-lat'].value, '37.391234');
    assert.equal(fields['physical-location-lon'].value, '-6.012345');
    assert.equal(fields['physical-location-accuracy'].value, '');
    assert.equal(markerPoint.lat, 37.391234);
    handlers.dragend();
    assert.equal(fields['physical-location-lat'].value, '37.400000');
    sandbox.disposePhysicalLocationMap();
    assert.equal(removed, true);
});

test('permite corregir el sitio activo enviando una orden con CSRF, no un PATCH inmediato', async () => {
    const { sandbox, fields } = dashboard();
    vm.runInContext("locationSites = [{ id: 4, code: 'test-site', active_deployment_count: 1 }];", sandbox);
    fields['physical-location-site-select'] = { value: '4' };
    fields['physical-location-confirm'] = { checked: true };
    fields['physical-location-coordinates'] = { open: true };
    fields['physical-location-feedback'] = {};
    let sent;
    sandbox.fetch = async (url, options) => {
        sent = { url, ...options };
        return { ok: true, json: async () => ({ target_site_name: 'Prueba' }) };
    };
    sandbox.window.setTimeout = () => {};
    await sandbox.submitPhysicalLocationCommand(1);
    assert.equal(sent.url, '/devices/1/location-commands');
    assert.equal(sent.method, 'POST');
    assert.equal(sent.headers['X-BirdMonitor-CSRF'], '1');
    assert.equal(JSON.parse(sent.body).coordinates.lat, 37.391234);
});

test('explica el rechazo del campo nuevo cuando sigue activo el backend anterior', () => {
    const { sandbox } = dashboard();
    const message = sandbox.locationApiErrorMessage({ detail: [{
        type: 'extra_forbidden', loc: ['body', 'coordinates'],
        msg: 'Extra inputs are not permitted', input: { lat: 37.3, lon: -6 }
    }] }, 422);
    assert.match(message, /versión anterior/);
    assert.match(message, /Reinicia BirdMonitor Backend/);
    assert.doesNotMatch(message, /\[object Object\]|37\.3/);
});

test('muestra errores de validación, texto y respuesta desconocida sin volcar objetos', () => {
    const { sandbox } = dashboard();
    assert.equal(sandbox.locationApiErrorMessage({ detail: 'Ya existe una orden pendiente' }, 409), 'Ya existe una orden pendiente');
    assert.equal(sandbox.locationApiErrorMessage({ detail: [
        { loc: ['body', 'coordinates', 'lat'], msg: 'Debe ser menor o igual a 90' },
        { loc: ['body', 'coordinates', 'lon'], msg: 'Campo obligatorio' }
    ] }, 422), 'Latitud: Debe ser menor o igual a 90 · Longitud: Campo obligatorio');
    assert.match(sandbox.locationApiErrorMessage({ detail: { unexpected: 'value' } }, 500), /HTTP 500/);
    assert.match(sandbox.locationApiErrorMessage(null, 502), /HTTP 502/);
});

test('un error 422 conserva el formulario y muestra texto escapado, sin anunciar éxito', async () => {
    const { sandbox, fields } = dashboard();
    vm.runInContext("locationSites = [{ id: 4, code: 'test-site', active_deployment_count: 1 }];", sandbox);
    fields['physical-location-site-select'] = { value: '4' };
    fields['physical-location-confirm'] = { checked: true };
    fields['physical-location-coordinates'] = { open: true };
    fields['physical-location-feedback'] = {};
    sandbox.fetch = async () => ({ ok: false, status: 422, json: async () => ({ detail: [
        { loc: ['body', 'coordinates', 'lat'], msg: '<error de prueba>' }
    ] }) });
    await sandbox.submitPhysicalLocationCommand(1);
    const html = fields['physical-location-feedback'].innerHTML;
    assert.match(html, /Latitud: &lt;error de prueba&gt;/);
    assert.doesNotMatch(html, /\[object Object\]|alert-success/);
    assert.equal(fields['physical-location-lat'].value, '37,391234');
    assert.equal(fields['physical-location-confirm'].checked, true);
});
