// Ejecutar: node --test tests/test_species_chart_ui.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function dashboard() {
    const charts = [];
    const makeCanvas = () => ({ getContext() { return { canvas: this }; } });
    const panel = {
        hidden: true, scrollTop: 0, writes: 0, html: '',
        set innerHTML(value) { this.html = value; this.writes++; },
        get innerHTML() { return this.html; },
    };
    const toggle = { setAttribute(key, value) { this[key] = value; } };
    const fields = {
        speciesChart: makeCanvas(),
        'species-chart-all-panel': panel,
        'species-chart-toggle': toggle,
    };
    class Chart {
        constructor(ctx, config) {
            this.canvas = ctx.canvas;
            this.data = config.data;
            this.options = config.options;
            this.hidden = new Set();
            this.updates = [];
            this.destroyed = false;
            charts.push(this);
        }
        update(mode) { this.updates.push(mode); }
        destroy() { this.destroyed = true; }
        getDataVisibility(index) { return !this.hidden.has(index); }
        toggleDataVisibility(index) {
            if (this.hidden.has(index)) this.hidden.delete(index);
            else this.hidden.add(index);
        }
    }
    const sandbox = {
        Chart, console,
        document: {
            getElementById: id => fields[id], addEventListener() {},
            createElement: () => ({ style: {} }), body: { appendChild() {} },
        },
        window: {
            innerWidth: 1200,
            location: { origin: 'http://localhost', hostname: 'localhost' },
            addEventListener() {},
        },
    };
    vm.createContext(sandbox);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/js/dashboard.js'), 'utf8'), sandbox);
    return { sandbox, charts, fields, panel, toggle, makeCanvas };
}

test('el sondeo sin cambios no recrea ni actualiza la rueda ni su lista', () => {
    const { sandbox, charts, panel } = dashboard();
    sandbox.updateChart({ Sparrow: 5, Dove: 2 });
    for (let i = 0; i < 15; i++) sandbox.updateChart({ Dove: 2, Sparrow: 5 });
    assert.equal(charts.length, 1);
    assert.equal(charts[0].destroyed, false);
    assert.equal(charts[0].updates.length, 0);
    assert.equal(panel.writes, 1);
});

test('actualiza los datos y porcentajes en la misma instancia, sin animacion', () => {
    const { sandbox, charts } = dashboard();
    sandbox.updateChart({ Sparrow: 5, Dove: 2 });
    sandbox.updateChart({ Sparrow: 6, Dove: 4 });
    const chart = charts[0];
    assert.equal(charts.length, 1);
    assert.deepEqual(Array.from(chart.data.datasets[0].data), [6, 4]);
    assert.deepEqual(chart.updates, ['none']);
    assert.equal(chart.options.animation, false);
    assert.equal(chart.options.plugins.tooltip.callbacks.label({
        chart, parsed: 6, label: 'Sparrow',
    }), 'Sparrow: 6 (60.0%)');
});

test('conserva colores y especies ocultadas cuando cambia el orden', () => {
    const { sandbox, charts } = dashboard();
    sandbox.updateChart({ Sparrow: 5, Dove: 2 });
    const chart = charts[0];
    const sparrowColor = chart.data.datasets[0].backgroundColor[0];
    chart.toggleDataVisibility(0);
    sandbox.updateChart({ Dove: 10, Sparrow: 5, Swift: 1 });
    assert.deepEqual(Array.from(chart.data.labels), ['Dove', 'Sparrow', 'Swift']);
    assert.equal(chart.getDataVisibility(0), true);
    assert.equal(chart.getDataVisibility(1), false);
    assert.equal(chart.getDataVisibility(2), true);
    assert.equal(chart.data.datasets[0].backgroundColor[1], sparrowColor);
    sandbox.updateChart({ Swift: 2 });
    sandbox.updateChart({ Swift: 2, Robin: 1 });
    assert.equal(chart.getDataVisibility(1), true);
});

test('mostrar mas conserva todas las especies de la rueda y no la actualiza', () => {
    const { sandbox, charts, panel, toggle } = dashboard();
    const counts = Object.fromEntries(Array.from({ length: 9 }, (_, i) => [`Bird ${i}`, 10 - i]));
    sandbox.updateChart(counts);
    sandbox.toggleSpeciesChartDetails();
    assert.equal(panel.hidden, false);
    assert.equal(toggle['aria-expanded'], 'true');
    panel.scrollTop = 120;
    sandbox.updateChart(counts);
    assert.equal(panel.scrollTop, 120);
    assert.equal(panel.writes, 2);
    assert.equal(charts[0].data.labels.length, 9);
    assert.equal(charts[0].options.plugins.legend.labels.filter({ index: 6 }), true);
    assert.equal(charts[0].options.plugins.legend.labels.filter({ index: 7 }), false);
    assert.equal(charts[0].updates.length, 0);
    sandbox.updateChart({ ...counts, 'Bird 0': 20 });
    assert.equal(panel.hidden, false);
    assert.equal(panel.scrollTop, 120);
    sandbox.toggleSpeciesChartDetails();
    assert.equal(panel.hidden, true);
    assert.equal(charts.length, 1);
});

test('vacia la grafica y oculta mostrar mas sin repetir actualizaciones vacias', () => {
    const { sandbox, charts, panel, toggle } = dashboard();
    sandbox.updateChart({ Sparrow: 1 });
    sandbox.updateChart({});
    sandbox.updateChart({});
    assert.equal(charts.length, 1);
    assert.equal(charts[0].data.labels.length, 0);
    assert.deepEqual(charts[0].updates, ['none']);
    assert.equal(panel.hidden, true);
    assert.equal(toggle.hidden, true);
});

test('recrea la grafica solo si el canvas ha sido reemplazado', () => {
    const { sandbox, charts, fields, makeCanvas } = dashboard();
    sandbox.updateChart({ Sparrow: 1 });
    fields.speciesChart = makeCanvas();
    sandbox.updateChart({ Sparrow: 1 });
    assert.equal(charts.length, 2);
    assert.equal(charts[0].destroyed, true);
    assert.equal(charts[1].canvas, fields.speciesChart);
});

test('ajusta la leyenda movil sin recrear la rueda ni tocar la lista', () => {
    const { sandbox, charts, panel } = dashboard();
    sandbox.updateChart({ Sparrow: 1 });
    sandbox.window.innerWidth = 500;
    sandbox.updateChart({ Sparrow: 1 });
    assert.equal(charts.length, 1);
    assert.equal(charts[0].options.plugins.legend.position, 'bottom');
    assert.deepEqual(charts[0].updates, ['none']);
    assert.equal(panel.writes, 1);
});

test('no crea ni destruye una grafica cuando no hay canvas visible', () => {
    const { sandbox, charts, fields } = dashboard();
    sandbox.updateChart({ Sparrow: 1 });
    delete fields.speciesChart;
    sandbox.updateChart({ Sparrow: 2 });
    assert.equal(charts.length, 1);
    assert.equal(charts[0].destroyed, false);
    assert.equal(charts[0].updates.length, 0);
});