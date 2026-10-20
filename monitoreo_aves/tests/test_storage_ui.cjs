const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function dashboard() {
    const panel = { innerHTML: '' };
    const sandbox = {
        console, AbortSignal,
        document: { getElementById: () => panel, addEventListener() {}, createElement: () => ({ style: {} }), body: { appendChild() {} } },
        window: { location: { origin: 'http://localhost', hostname: 'localhost' }, addEventListener() {} },
    };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/js/dashboard.js'), 'utf8'), sandbox);
    return { sandbox, panel };
}

const node = () => ({ device_name: 'birdmonitor', measured_at: new Date().toISOString(), stale: false,
    total_bytes: 128 * 1024 ** 3, free_bytes: 96 * 1024 ** 3, recordings_bytes: 5.4 * 1024 ** 3, recordings_count: 100 });

test('storage distinguishes unavailable measurements from empty recordings', () => {
    const { sandbox } = dashboard();
    assert.equal(sandbox.formatStorageSize(null), 'No disponible');
    assert.equal(sandbox.formatStorageSize(0), '0,0 GiB');
    const html = sandbox.nodeStorageContent([{ ...node(), recordings_bytes: 0, recordings_count: 0 }]);
    assert.match(html, /96,0 GiB/);
    assert.match(html, /0 archivos WAV/);
    assert.doesNotMatch(html, /Sin actualización reciente/);
});

test('old measurements are marked stale and node names are escaped', () => {
    const { sandbox } = dashboard();
    const html = sandbox.nodeStorageContent([{ ...node(), device_name: '<script>bad</script>',
        measured_at: new Date(Date.now() - 20 * 60 * 1000).toISOString() }]);
    assert.match(html, /Sin actualización reciente/);
    assert.doesNotMatch(html, /<script>/);
    assert.match(sandbox.nodeStorageContent([]), /Esperando la primera medición/);
});

test('failed refresh retains the last measurement with an explicit warning', async () => {
    const { sandbox, panel } = dashboard();
    sandbox.fetch = async () => ({ ok: true, json: async () => ({ nodes: [node()] }) });
    await sandbox.refreshNodeStorage();
    assert.match(panel.innerHTML, /96,0 GiB/);
    sandbox.fetch = async () => { throw new Error('offline'); };
    await sandbox.refreshNodeStorage();
    assert.match(panel.innerHTML, /96,0 GiB/);
    assert.match(panel.innerHTML, /No se pudo consultar una actualización/);
});
