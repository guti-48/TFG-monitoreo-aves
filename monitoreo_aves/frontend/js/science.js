// Pestanas del Analisis cientifico (compartido por la web y el movil).
// Envuelve renderScienceView sin reescribirla: "Resumen" es la vista de siempre y "Sonido" muestra
// como evolucionan los indices acusticos en el tiempo (datos de /analytics/acoustic-series).
(() => {
  if (typeof renderScienceView !== 'function') return;
  const originalRender = renderScienceView;

  const TABS = [
    ['resumen', 'Resumen', 'bi-speedometer2'],
    ['sonido', 'Sonido', 'bi-soundwave'],
  ];
  const GREEN = '#2f6f4f';
  let activeTab = 'resumen';
  let charts = [];
  let request = 0;

  const number = (value, decimals = 2) => (value === null || value === undefined ? '–' : Number(value).toLocaleString('es-ES', { maximumFractionDigits: decimals }));
  const dayNumber = (iso) => Math.round(Date.parse(`${iso}T00:00:00Z`) / 86400000);
  const dayLabel = (n) => new Date(n * 86400000).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', timeZone: 'UTC' });
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const destroyCharts = () => { charts.forEach((chart) => chart.destroy()); charts = []; };

  window.renderScienceView = async function (container) {
    destroyCharts();
    request += 1;
    container.innerHTML = `
      <div class="science-tabs" role="tablist" aria-label="Secciones del análisis">
        ${TABS.map(([id, label, icon]) => `<button type="button" role="tab" class="science-tab" data-tab="${id}" aria-selected="false"><i class="bi ${icon}" aria-hidden="true"></i><span>${label}</span></button>`).join('')}
      </div>
      <div id="science-panel-resumen" class="science-panel" role="tabpanel"></div>
      <div id="science-panel-sonido" class="science-panel" role="tabpanel" hidden></div>`;
    const panels = {
      resumen: container.querySelector('#science-panel-resumen'),
      sonido: container.querySelector('#science-panel-sonido'),
    };
    let soundLoaded = false;

    const show = (tab) => {
      activeTab = tab;
      container.querySelectorAll('.science-tab').forEach((button) => button.setAttribute('aria-selected', String(button.dataset.tab === tab)));
      Object.entries(panels).forEach(([id, panel]) => { panel.hidden = id !== tab; });
      if (tab === 'sonido' && !soundLoaded) { soundLoaded = true; loadSound(panels.sonido); }
      window.dispatchEvent(new Event('resize')); // graficos y mapa se reajustan al volver a mostrarse
    };
    container.querySelector('.science-tabs').addEventListener('click', (event) => {
      const button = event.target.closest('.science-tab');
      if (button) show(button.dataset.tab);
    });

    // El resumen se renderiza visible (Chart.js y el mapa necesitan medir su contenedor) y despues se vuelve a la pestana activa.
    const wanted = activeTab;
    show('resumen');
    await originalRender(panels.resumen);
    if (wanted !== 'resumen' && panels.resumen.isConnected) show(wanted);
  };

  async function loadSound(panel) {
    const ticket = ++request;
    panel.innerHTML = '<div class="science-loading"><div class="spinner-border spinner-border-sm" role="status"></div><span>Cargando la serie de índices…</span></div>';
    let data;
    try {
      const params = selectedScienceDeviceId ? { device_id: selectedScienceDeviceId } : {};
      const response = await fetch(locationAwareUrl('/analytics/acoustic-series', params), { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      data = await response.json();
    } catch (error) {
      if (ticket === request && panel.isConnected) panel.innerHTML = `<div class="alert alert-warning">No se pudo cargar la serie de índices: ${escapeHtml(error.message)}</div>`;
      return;
    }
    if (ticket !== request || !panel.isConnected) return;
    if (!data.available) {
      const legacy = data.legacy_excluded ? ` Hay ${number(data.legacy_excluded, 0)} muestras del método antiguo, que no se pueden comparar.` : '';
      panel.innerHTML = `<div class="alert alert-secondary">${escapeHtml(data.reason || 'Sin datos')}.${legacy}</div>`;
      return;
    }
    renderSound(panel, data);
  }

  function renderSound(panel, data) {
    const legacy = data.legacy_excluded ? ` · ${number(data.legacy_excluded, 0)} muestras antiguas excluidas (unidades no comparables)` : '';
    panel.innerHTML = `
      <section class="science-sound">
        <header class="science-sound-head">
          <h4>Paisaje sonoro en el tiempo</h4>
          <p>${number(data.samples, 0)} muestras · ${data.days} días · método ${escapeHtml(data.metrics_version)}${legacy}</p>
        </header>
        <div class="science-chips" role="radiogroup" aria-label="Índice acústico">
          ${data.indices.map((index) => `<button type="button" role="radio" class="science-chip" data-key="${escapeHtml(index.key)}" aria-checked="false" title="${escapeHtml(index.description)}">${escapeHtml(index.label)}</button>`).join('')}
        </div>
        <p class="science-index-note" id="science-index-note"></p>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-daily-chart" role="img"></canvas></div>
          <figcaption id="science-daily-caption"></figcaption>
        </figure>
        <figure class="science-figure">
          <div class="science-canvas"><canvas id="science-hourly-chart" role="img"></canvas></div>
          <figcaption id="science-hourly-caption"></figcaption>
        </figure>
      </section>`;

    const chips = panel.querySelectorAll('.science-chip');
    const select = (key) => {
      chips.forEach((chip) => chip.setAttribute('aria-checked', String(chip.dataset.key === key)));
      drawIndex(panel, data, key);
    };
    panel.querySelector('.science-chips').addEventListener('click', (event) => {
      const chip = event.target.closest('.science-chip');
      if (chip) select(chip.dataset.key);
    });
    select(data.indices.some((index) => index.key === 'bio') ? 'bio' : data.indices[0].key);
  }

  function drawIndex(panel, data, key) {
    destroyCharts();
    const index = data.indices.find((item) => item.key === key);
    const fixedRange = key === 'ndsi' ? { min: -1, max: 1 } : {}; // el NDSI esta definido entre -1 y 1
    const animation = reducedMotion() ? false : { duration: 300 };
    const grid = { color: 'rgba(95, 111, 101, .15)' };
    const font = { family: "'DM Sans', system-ui, sans-serif" };

    const daily = data.daily.filter((row) => row[key] !== null).map((row) => ({ x: dayNumber(row.date), y: row[key], n: row.n, low: row.low_sample }));
    const hourly = Array.from({ length: 24 }, (_, hour) => data.hourly.find((row) => row.hour === hour) || { hour, n: 0, [key]: null });

    const values = hourly.filter((row) => row[key] !== null);
    const peak = values.reduce((best, row) => (row[key] > best[key] ? row : best), values[0]);
    const trough = values.reduce((worst, row) => (row[key] < worst[key] ? row : worst), values[0]);
    panel.querySelector('#science-index-note').textContent = `${index.description} Por hora, el máximo es a las ${peak.hour} h (${number(peak[key])}) y el mínimo a las ${trough.hour} h (${number(trough[key])}).`;
    panel.querySelector('#science-daily-caption').textContent = `Fig. 1 — Media diaria de ${index.label}. Un punto hueco indica menos de ${data.min_samples_per_day} muestras ese día; la línea discontinua une días separados por huecos sin datos.`;
    panel.querySelector('#science-hourly-caption').textContent = `Fig. 2 — Perfil medio de ${index.label} por hora del día (hora local del nodo), con todas las muestras del periodo.`;
    panel.querySelector('#science-daily-chart').setAttribute('aria-label', `Evolución diaria de ${index.label} entre ${data.daily[0].date} y ${data.daily[data.daily.length - 1].date}`);
    panel.querySelector('#science-hourly-chart').setAttribute('aria-label', `Perfil por hora de ${index.label}`);

    charts.push(new Chart(panel.querySelector('#science-daily-chart'), {
      type: 'line',
      data: {
        datasets: [{
          data: daily,
          borderColor: GREEN,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: (ctx) => (ctx.raw?.low ? '#ffffff' : GREEN),
          pointBorderColor: GREEN,
          segment: { borderDash: (ctx) => (ctx.p1.parsed.x - ctx.p0.parsed.x > 1.5 ? [4, 4] : undefined) },
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (items) => dayLabel(items[0].parsed.x), label: (item) => `${index.label}: ${number(item.parsed.y, 3)} (${item.raw.n} muestras)` } },
        },
        scales: {
          x: {
            type: 'linear',
            bounds: 'data',
            grid,
            // Ticks a intervalos iguales entre el primer y el ultimo dia: el automatico acababa pisando la ultima etiqueta.
            afterBuildTicks: (scale) => {
              const count = window.innerWidth < 600 ? 4 : 7;
              scale.ticks = Array.from({ length: count }, (_, i) => ({ value: Math.round(scale.min + ((scale.max - scale.min) * i) / (count - 1)) }));
            },
            ticks: { maxRotation: 0, callback: (value) => dayLabel(value), font },
          },
          y: { ...fixedRange, grid, title: { display: true, text: index.label, font }, ticks: { font } },
        },
      },
    }));

    charts.push(new Chart(panel.querySelector('#science-hourly-chart'), {
      type: 'line',
      data: {
        labels: hourly.map((row) => `${row.hour}`),
        datasets: [{
          data: hourly.map((row) => row[key]),
          borderColor: GREEN,
          backgroundColor: 'rgba(47, 111, 79, .14)',
          fill: 'start', // hacia el borde inferior del eje, no hacia el cero (con valores negativos engañaria)
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { title: (items) => `${items[0].label}:00 h`, label: (item) => `${index.label}: ${number(item.parsed.y, 3)} (${hourly[item.dataIndex].n} muestras)` } },
        },
        scales: {
          x: { grid: { display: false }, title: { display: true, text: 'Hora del día', font }, ticks: { font, maxTicksLimit: 12 } },
          y: { ...fixedRange, grid, title: { display: true, text: index.label, font }, ticks: { font } },
        },
      },
    }));
  }
})();
