const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function dashboard() {
    const fields = {};
    const sandbox = { console, document: {
        getElementById: id => fields[id], addEventListener() {},
        createElement: () => ({ style: {}, dataset: {}, remove() {} }), body: { appendChild() {} },
    }, window: { location: { origin: 'http://localhost', hostname: 'localhost' }, addEventListener() {} } };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/js/dashboard.js'), 'utf8'), sandbox);
    return { sandbox, fields };
}

test('a conflict replaces quick review controls with an explicit resolution action', () => {
    const { sandbox } = dashboard();
    const detection = { id: 5, review_sync: { conflict: true }, review: { status: 'doubtful' } };
    assert.match(sandbox.buildReviewBadge(detection), /Revisiones en conflicto/);
    const actions = sandbox.buildReviewActions(detection);
    assert.match(actions, /Comparar y resolver/);
    assert.doesNotMatch(actions, /quickReviewDetection/);
});

test('an open correction keeps the version seen when it opened', async () => {
    const { sandbox, fields } = dashboard();
    fields['correction-dialog'] = { dataset: { reviewVersions: '["old-version"]' } };
    vm.runInContext('detectionCache.set(5, {review_sync:{heads:["new-version"]}})', sandbox);
    let payload;
    sandbox.fetch = async (url, options) => {
        payload = JSON.parse(options.body);
        return { ok: true, json: async () => ({}) };
    };
    await sandbox.patchDetectionReview(5, {status: 'noise'});
    assert.deepEqual(payload.base_versions, ['old-version']);
});

test('a stale conflict resolution stays open and asks to reload the alternatives', async () => {
    const { sandbox, fields } = dashboard();
    let removed = false;
    fields['review-conflict-dialog'] = { reviewHeads: ['a','b'], remove() { removed = true; } };
    fields['review-conflict-feedback'] = {};
    sandbox.fetch = async () => ({ok:false,status:409});
    const button = {};
    await sandbox.resolveReviewConflict(5,'a',button);
    assert.equal(removed,false);
    assert.equal(button.disabled,false);
    assert.match(fields['review-conflict-feedback'].textContent,/Han llegado más revisiones/);
});
